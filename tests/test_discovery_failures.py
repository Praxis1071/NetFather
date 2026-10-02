"""Distinguish failed discovery sources from a valid empty inventory."""
from __future__ import annotations

import subprocess
import sys
from types import SimpleNamespace

import pytest

from network.discovery import (
    DiscoveredHost,
    DiscoveryError,
    _parse_ip_neigh_output,
    _scan_linux,
    _scan_scapy,
    scan_network,
    scan_network_report,
)


@pytest.mark.parametrize("failure", ["missing", "timeout", "oserror", "exit"])
def test_passive_source_failure_is_not_a_successful_empty_scan(monkeypatch, failure):
    monkeypatch.setattr("network.discovery.shutil.which", lambda _: None if failure == "missing" else "/usr/bin/ip")

    def run(*args, **kwargs):
        if failure == "timeout":
            raise subprocess.TimeoutExpired(args[0], 5)
        if failure == "oserror":
            raise OSError("ip unavailable")
        return SimpleNamespace(returncode=1, stdout="")

    monkeypatch.setattr("network.discovery.subprocess.run", run)
    report = scan_network_report(mode="passive")
    assert report.hosts == ()
    assert report.complete is False
    assert report.warnings


def test_successful_empty_neighbor_tables_are_complete(monkeypatch):
    calls = []
    monkeypatch.setattr("network.discovery.shutil.which", lambda _: "/usr/bin/ip")
    monkeypatch.setattr("network.discovery._run_process", lambda args, _: calls.append(args) or "")
    report = scan_network_report(mode="passive")
    assert report.complete is True
    assert report.hosts == ()
    assert report.warnings == ()
    assert len(calls) == 2
    assert "-6" in calls[1]


def test_one_failed_neighbor_family_does_not_report_a_complete_scan(monkeypatch):
    monkeypatch.setattr("network.discovery.shutil.which", lambda _: "/usr/bin/ip")
    monkeypatch.setattr("network.discovery._run_process", lambda args, _: None if "-6" in args else "")
    with pytest.raises(DiscoveryError):
        _scan_linux(5)


@pytest.mark.parametrize("failed_source", ["passive", "active"])
def test_hybrid_preserves_the_other_sources_positive_observations(monkeypatch, failed_source):
    host = DiscoveredHost("192.168.1.20", mac="aa:bb:cc:dd:ee:20")

    def failed(*args):
        raise PermissionError("source unavailable")

    monkeypatch.setattr("network.discovery._scan_linux", failed if failed_source == "passive" else lambda _: [host])
    monkeypatch.setattr("network.discovery._scan_scapy", failed if failed_source == "active" else lambda *_: [host])
    report = scan_network_report(mode="hybrid", subnet="192.168.1.0/24", vendor_detection=False)
    assert report.hosts == (host,)
    assert report.complete is False
    assert "source unavailable" in report.warnings[0]
    assert scan_network(mode="hybrid", subnet="192.168.1.0/24", vendor_detection=False) == [host]


def test_missing_active_subnet_is_reported(monkeypatch):
    monkeypatch.setattr("network.discovery.infer_local_subnet", lambda: None)
    report = scan_network_report(mode="active")
    assert report.complete is False
    assert "subnet" in report.warnings[0]


def test_active_permission_failure_is_reported(monkeypatch):
    def denied(*args, **kwargs):
        raise PermissionError("raw socket denied")

    class Packet:
        def __init__(self, **kwargs):
            pass

        def __truediv__(self, other):
            return self

    monkeypatch.setitem(sys.modules, "scapy.all", SimpleNamespace(ARP=Packet, Ether=Packet, srp=denied))
    with pytest.raises(DiscoveryError, match="raw socket denied"):
        _scan_scapy("192.168.1.0/24", 1)


def test_missing_scapy_is_reported(monkeypatch):
    monkeypatch.setitem(sys.modules, "scapy.all", None)
    with pytest.raises(DiscoveryError, match="Scapy is not installed"):
        _scan_scapy("192.168.1.0/24", 1)


@pytest.mark.parametrize("subnet", ["192.168.0.0/15", "fe80::/64", "invalid"])
def test_invalid_active_target_is_not_silently_empty(subnet):
    with pytest.raises(DiscoveryError):
        _scan_scapy(subnet, 1)


@pytest.mark.parametrize("state", ["FAILED", "INCOMPLETE"])
def test_failed_neighbor_records_do_not_refresh_online_state(state):
    assert _parse_ip_neigh_output(f"192.168.1.20 dev eth0 lladdr aa:bb:cc:dd:ee:20 {state}\n") == []


def test_deep_warnings_reach_the_report_without_losing_discovery(monkeypatch):
    host = DiscoveredHost("192.168.1.20", mac="aa:bb:cc:dd:ee:20")
    monkeypatch.setattr("network.discovery._scan_linux", lambda _: [host])
    monkeypatch.setattr("network.discovery._scan_scapy", lambda *_: [])
    monkeypatch.setattr("network.discovery._apply_deep_scan", lambda hosts, *args, **kwargs: (hosts, ("Nmap unavailable",)))
    report = scan_network_report(mode="deep", subnet="192.168.1.0/24", vendor_detection=False)
    assert report.hosts == (host,)
    assert report.warnings == ("Nmap unavailable",)
    assert not report.complete
