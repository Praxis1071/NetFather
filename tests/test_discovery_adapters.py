"""Optional Linux discovery adapters degrade explicitly and never invent presence."""
from types import SimpleNamespace
import sys
import subprocess

import pytest

from core.operations import CancellationToken
from network.enrichment import parse_leases, resolve_local_name
from network.network_manager import NetworkManagerObserver
from network.deep_scan import run_deep_scan


@pytest.mark.parametrize("failure", ["exit", "timeout", "oserror", "xml"])
def test_deep_inventory_subprocess_errors_are_explicit(monkeypatch, failure):
    monkeypatch.setattr("network.deep_scan.nmap_available", lambda: True)
    monkeypatch.setattr("network.deep_scan.privileged", lambda: False)
    def run(*args, **kwargs):
        if failure == "timeout":
            raise subprocess.TimeoutExpired(args[0], 1)
        if failure == "oserror":
            raise OSError("unavailable")
        return SimpleNamespace(returncode=3 if failure == "exit" else 0, stdout="not XML", stderr="authorization denied")
    monkeypatch.setattr("network.deep_scan.subprocess.run", run)
    report = run_deep_scan("192.168.1.0/24")
    assert not report.hosts and report.warnings


def test_expired_isc_lease_does_not_enrich(monkeypatch):
    raw = '''lease 192.168.1.20 {
      ends 1 2020/01/01 12:00:00;
      binding state active;
      hardware ethernet 02:00:00:00:00:20;
      client-hostname "tablet";
    }'''
    assert parse_leases(raw, now=2_000_000_000) == {}


def test_local_name_enrichment_is_bounded_and_uses_mdns_llmnr(monkeypatch):
    calls = []
    monkeypatch.setattr("network.enrichment.shutil.which", lambda name: "/usr/bin/" + name)
    def run(args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(returncode=0, stdout="192.168.1.20: tablet.local\n")
    monkeypatch.setattr("network.enrichment.run_process", run)
    assert resolve_local_name("192.168.1.20", "eth0", token=CancellationToken()) == "tablet.local"
    assert "--protocol=mdns" in calls[0][0] and "--protocol=llmnr" in calls[0][0]
    assert calls[0][1]["timeout"] == 2
    assert resolve_local_name("8.8.8.8", "eth0") is None
    assert len(calls) == 1


def test_networkmanager_signals_and_disconnect_lifecycle(monkeypatch):
    class Object:
        def __init__(self):
            self.callbacks, self.disconnected = {}, []
        def connect(self, signal, callback):
            self.callbacks[signal] = callback
            return signal
        def disconnect(self, handler):
            self.disconnected.append(handler)
    device, client = Object(), Object()
    client.get_nm_running = lambda: True
    client.get_devices = lambda: [device]
    monkeypatch.setitem(sys.modules, "gi", SimpleNamespace(require_version=lambda *_: None))
    factory = SimpleNamespace(new_finish=lambda _: client,
        new_async=lambda _cancel, callback, _data: callback(None, object()))
    monkeypatch.setitem(sys.modules, "gi.repository", SimpleNamespace(NM=SimpleNamespace(Client=factory),
        Gio=SimpleNamespace(Cancellable=lambda: SimpleNamespace(cancel=lambda: None))))
    changed = []
    observer = NetworkManagerObserver(lambda: changed.append(True))
    assert observer.start()
    device.callbacks["state-changed"]()
    client.callbacks["notify::active-connections"]()
    assert len(changed) == 3
    observer.stop()
    assert len(device.disconnected) == 4 and len(client.disconnected) == 3


def test_missing_networkmanager_is_an_explicit_optional_capability(monkeypatch):
    monkeypatch.setitem(sys.modules, "gi", None)
    observer = NetworkManagerObserver(lambda: None)
    assert not observer.start()
    assert "periodic discovery continues" in observer.warning
    observer.stop()
