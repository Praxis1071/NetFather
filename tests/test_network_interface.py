"""
network.interface için testler.

Hiçbir test gerçek ağ bağlantısına veya sistemde `ip` komutunun kurulu
olmasına bağımlı değildir:
    - Parser testleri saf string girdileriyle çalışır.
    - Wrapper testleri `subprocess.run` ve `shutil.which`'i mock'lar.
"""

from __future__ import annotations

import subprocess

import pytest

import network.interface as interface_module
from network.interface import (
    NetworkStatus,
    _parse_route_get_output,
    _run_ip_route_get,
    get_network_status,
)

# ---------------------------------------------------------------------------
# _parse_route_get_output: saf parser testleri
# ---------------------------------------------------------------------------


def test_parse_standard_output_with_gateway() -> None:
    raw = "8.8.8.8 via 192.168.1.1 dev wlan0 src 192.168.1.50 uid 1000 \n    cache \n"

    status = _parse_route_get_output(raw)

    assert status.interface == "wlan0"
    assert status.local_ip == "192.168.1.50"
    assert status.gateway == "192.168.1.1"


def test_parse_output_without_gateway() -> None:
    # Hedef doğrudan bağlı bir ağdaysa 'via' kısmı görünmeyebilir.
    raw = "192.168.1.5 dev eth0 src 192.168.1.50 uid 1000 \n"

    status = _parse_route_get_output(raw)

    assert status.interface == "eth0"
    assert status.local_ip == "192.168.1.50"
    assert status.gateway is None


def test_parse_ethernet_interface_name() -> None:
    raw = "8.8.8.8 via 10.0.0.1 dev enp3s0 src 10.0.0.42 \n"

    status = _parse_route_get_output(raw)

    assert status.interface == "enp3s0"
    assert status.local_ip == "10.0.0.42"
    assert status.gateway == "10.0.0.1"


def test_parse_empty_output_returns_empty_status() -> None:
    status = _parse_route_get_output("")

    assert status == NetworkStatus()


def test_parse_malformed_output_returns_empty_status() -> None:
    raw = "RTNETLINK answers: Network is unreachable\n"

    status = _parse_route_get_output(raw)

    assert status == NetworkStatus()


def test_parse_never_raises_on_garbage_input() -> None:
    # Parser hiçbir koşulda exception fırlatmamalı; en kötü ihtimalle
    # boş bir NetworkStatus döner.
    status = _parse_route_get_output("############\n\t\t???")
    assert status == NetworkStatus()


# ---------------------------------------------------------------------------
# _run_ip_route_get: subprocess mock'lı wrapper testleri
# ---------------------------------------------------------------------------


def test_run_ip_route_get_returns_none_when_ip_binary_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(interface_module.shutil, "which", lambda _cmd: None)

    result = _run_ip_route_get()

    assert result is None


def test_run_ip_route_get_returns_stdout_on_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(interface_module.shutil, "which", lambda _cmd: "/usr/sbin/ip")

    expected_stdout = "8.8.8.8 via 192.168.1.1 dev wlan0 src 192.168.1.50\n"

    def fake_run(*_args, **_kwargs):
        return subprocess.CompletedProcess(
            args=["ip", "route", "get", "8.8.8.8"],
            returncode=0,
            stdout=expected_stdout,
            stderr="",
        )

    monkeypatch.setattr(interface_module.subprocess, "run", fake_run)

    result = _run_ip_route_get()

    assert result == expected_stdout


def test_run_ip_route_get_returns_none_on_nonzero_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(interface_module.shutil, "which", lambda _cmd: "/usr/sbin/ip")

    def fake_run(*_args, **_kwargs):
        return subprocess.CompletedProcess(
            args=["ip", "route", "get", "8.8.8.8"],
            returncode=2,
            stdout="",
            stderr="RTNETLINK answers: Network is unreachable\n",
        )

    monkeypatch.setattr(interface_module.subprocess, "run", fake_run)

    result = _run_ip_route_get()

    assert result is None


def test_run_ip_route_get_returns_none_on_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(interface_module.shutil, "which", lambda _cmd: "/usr/sbin/ip")

    def fake_run(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(cmd="ip route get 8.8.8.8", timeout=3)

    monkeypatch.setattr(interface_module.subprocess, "run", fake_run)

    result = _run_ip_route_get()

    assert result is None


def test_run_ip_route_get_returns_none_on_os_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(interface_module.shutil, "which", lambda _cmd: "/usr/sbin/ip")

    def fake_run(*_args, **_kwargs):
        raise OSError("permission denied")

    monkeypatch.setattr(interface_module.subprocess, "run", fake_run)

    result = _run_ip_route_get()

    assert result is None


# ---------------------------------------------------------------------------
# get_network_status: uçtan uca (wrapper mock'lı) entegrasyon testleri
# ---------------------------------------------------------------------------


def test_get_network_status_returns_parsed_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        interface_module,
        "_run_ip_route_get",
        lambda: "8.8.8.8 via 192.168.1.1 dev wlan0 src 192.168.1.50\n",
    )

    status = get_network_status()

    assert status.interface == "wlan0"
    assert status.local_ip == "192.168.1.50"
    assert status.gateway == "192.168.1.1"


def test_get_network_status_returns_empty_when_detection_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(interface_module, "_run_ip_route_get", lambda: None)

    status = get_network_status()

    assert status == NetworkStatus()


def test_get_network_status_never_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    # 'ip' hiç kurulu olmasa bile get_network_status() exception fırlatmamalı.
    monkeypatch.setattr(interface_module.shutil, "which", lambda _cmd: None)

    status = get_network_status()

    assert status == NetworkStatus()
