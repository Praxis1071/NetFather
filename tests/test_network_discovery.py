"""
network.discovery için testler.

Hiçbir test gerçek ağ bağlantısına veya sistemde `ip` komutunun kurulu
olmasına bağımlı değildir:
    - Parser testleri saf string girdileriyle çalışır.
    - Wrapper testleri `subprocess.run` ve `shutil.which`'i mock'lar.

Scapy bu testlerde hiçbir şekilde import edilmez veya referans edilmez;
bu dosya yalnızca basic (ip neigh) discovery'yi test eder.
"""

from __future__ import annotations

import subprocess

import pytest

import network.discovery as discovery_module
from network.discovery import (
    DiscoveredHost,
    _normalize_discovery_mac,
    _parse_ip_neigh_output,
    _parse_neigh_line,
    _run_ip_neigh,
    scan_network,
)

# ---------------------------------------------------------------------------
# 1-2) Standart satır / MAC adresli kayıt
# ---------------------------------------------------------------------------


def test_parse_standard_line_with_mac() -> None:
    host = _parse_neigh_line("192.168.1.1 dev eth0 lladdr aa:bb:cc:dd:ee:ff REACHABLE")

    assert host == DiscoveredHost(
        ip="192.168.1.1", interface="eth0", mac="aa:bb:cc:dd:ee:ff", state="REACHABLE"
    )


def test_parse_line_normalizes_mac_to_lowercase() -> None:
    host = _parse_neigh_line("192.168.1.10 dev eth0 lladdr AA-BB-CC-DD-EE-FF STALE")

    assert host is not None
    assert host.mac == "aa:bb:cc:dd:ee:ff"


# ---------------------------------------------------------------------------
# 3) MAC adresi olmayan kayıt
# ---------------------------------------------------------------------------


def test_parse_line_without_mac_is_kept() -> None:
    host = _parse_neigh_line("192.168.1.20 dev eth0 FAILED")

    assert host == DiscoveredHost(ip="192.168.1.20", interface="eth0", mac=None, state="FAILED")


# ---------------------------------------------------------------------------
# 4) Farklı neighbor state'leri (bilinen + bilinmeyen)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "state",
    [
        "REACHABLE",
        "STALE",
        "DELAY",
        "PROBE",
        "FAILED",
        "INCOMPLETE",
        "NOARP",
        "PERMANENT",
        "SOME_FUTURE_STATE",  # bilinmeyen ama syntactically geçerli
    ],
)
def test_parse_preserves_arbitrary_state_verbatim(state: str) -> None:
    host = _parse_neigh_line(f"192.168.1.30 dev wlan0 lladdr aa:aa:aa:aa:aa:aa {state}")

    assert host is not None
    assert host.state == state


# ---------------------------------------------------------------------------
# 5) Birden fazla kayıt
# ---------------------------------------------------------------------------


def test_parse_multiple_lines() -> None:
    raw = (
        "192.168.1.1 dev eth0 lladdr aa:bb:cc:dd:ee:ff REACHABLE\n"
        "192.168.1.10 dev eth0 lladdr 11:22:33:44:55:66 STALE\n"
        "192.168.1.20 dev eth0 FAILED\n"
        "192.168.1.30 dev wlan0 lladdr aa:aa:aa:aa:aa:aa DELAY\n"
    )

    hosts = _parse_ip_neigh_output(raw)

    assert len(hosts) == 4
    ips = {h.ip for h in hosts}
    assert ips == {"192.168.1.1", "192.168.1.10", "192.168.1.20", "192.168.1.30"}


# ---------------------------------------------------------------------------
# 6) Farklı interface isimleri
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("interface", ["eth0", "wlan0", "enp3s0", "wlp2s0"])
def test_parse_various_interface_names(interface: str) -> None:
    host = _parse_neigh_line(f"192.168.1.5 dev {interface} lladdr aa:bb:cc:dd:ee:ff REACHABLE")

    assert host is not None
    assert host.interface == interface


# ---------------------------------------------------------------------------
# 7) Boş çıktı
# ---------------------------------------------------------------------------


def test_parse_empty_output_returns_empty_list() -> None:
    assert _parse_ip_neigh_output("") == []


def test_parse_whitespace_only_output_returns_empty_list() -> None:
    assert _parse_ip_neigh_output("\n\n   \n") == []


# ---------------------------------------------------------------------------
# 8) Garbage / malformed çıktı
# ---------------------------------------------------------------------------


def test_parse_single_garbage_line_is_skipped() -> None:
    assert _parse_neigh_line("###garbage###") is None


def test_parse_line_missing_dev_keyword_is_skipped() -> None:
    assert _parse_neigh_line("192.168.1.1 wlan0 lladdr aa:bb:cc:dd:ee:ff REACHABLE") is None


def test_parse_mixed_garbage_and_valid_lines() -> None:
    raw = (
        "###garbage###\n"
        "192.168.1.1 dev eth0 lladdr aa:bb:cc:dd:ee:ff REACHABLE\n"
        "\t\t???\n"
        "192.168.1.20 dev eth0 FAILED\n"
    )

    hosts = _parse_ip_neigh_output(raw)

    assert len(hosts) == 2
    assert {h.ip for h in hosts} == {"192.168.1.1", "192.168.1.20"}


# ---------------------------------------------------------------------------
# 9-12) Wrapper: ip yok / non-zero exit / timeout / OSError
# ---------------------------------------------------------------------------


def test_run_ip_neigh_returns_none_when_ip_binary_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(discovery_module.shutil, "which", lambda _cmd: None)

    assert _run_ip_neigh(timeout_seconds=5) is None


def test_run_ip_neigh_returns_stdout_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(discovery_module.shutil, "which", lambda _cmd: "/usr/sbin/ip")
    expected_stdout = "192.168.1.1 dev eth0 lladdr aa:bb:cc:dd:ee:ff REACHABLE\n"

    def fake_run(*_args, **_kwargs):
        return subprocess.CompletedProcess(
            args=["ip", "neigh"], returncode=0, stdout=expected_stdout, stderr=""
        )

    monkeypatch.setattr(discovery_module.subprocess, "run", fake_run)

    assert _run_ip_neigh(timeout_seconds=5) == expected_stdout


def test_run_ip_neigh_returns_none_on_nonzero_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(discovery_module.shutil, "which", lambda _cmd: "/usr/sbin/ip")

    def fake_run(*_args, **_kwargs):
        return subprocess.CompletedProcess(
            args=["ip", "neigh"], returncode=1, stdout="", stderr="some error\n"
        )

    monkeypatch.setattr(discovery_module.subprocess, "run", fake_run)

    assert _run_ip_neigh(timeout_seconds=5) is None


def test_run_ip_neigh_returns_none_on_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(discovery_module.shutil, "which", lambda _cmd: "/usr/sbin/ip")

    def fake_run(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(cmd="ip neigh", timeout=5)

    monkeypatch.setattr(discovery_module.subprocess, "run", fake_run)

    assert _run_ip_neigh(timeout_seconds=5) is None


def test_run_ip_neigh_returns_none_on_os_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(discovery_module.shutil, "which", lambda _cmd: "/usr/sbin/ip")

    def fake_run(*_args, **_kwargs):
        raise OSError("permission denied")

    monkeypatch.setattr(discovery_module.subprocess, "run", fake_run)

    assert _run_ip_neigh(timeout_seconds=5) is None


# ---------------------------------------------------------------------------
# 13) Parser exception sızdırmıyor
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        "\n\n\n",
        "###totally_broken###",
        "192.168.1.1",
        "192.168.1.1 dev",
        "dev eth0 lladdr aa:bb:cc:dd:ee:ff REACHABLE",
        "\x00\x01\x02 garbage bytes-ish",
        "192.168.1.1 dev eth0 lladdr",  # 'lladdr' var ama MAC eksik
    ],
)
def test_parser_never_raises_on_malformed_input(raw: str) -> None:
    # Hiçbiri exception fırlatmamalı; en kötü ihtimalle boş/kısmi sonuç.
    result = _parse_ip_neigh_output(raw)
    assert isinstance(result, list)


# ---------------------------------------------------------------------------
# 14) scan_network güvenli fallback
# ---------------------------------------------------------------------------


def test_scan_network_returns_empty_list_when_detection_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(discovery_module, "_run_ip_neigh", lambda timeout_seconds: None)

    assert scan_network(platform_name="linux") == []


def test_scan_network_returns_parsed_results(monkeypatch: pytest.MonkeyPatch) -> None:
    raw = "192.168.1.1 dev eth0 lladdr aa:bb:cc:dd:ee:ff REACHABLE\n"
    monkeypatch.setattr(discovery_module, "_run_ip_neigh", lambda timeout_seconds: raw)

    hosts = scan_network(platform_name="linux")

    assert len(hosts) == 1
    assert hosts[0].ip == "192.168.1.1"


def test_scan_network_never_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(discovery_module.shutil, "which", lambda _cmd: None)

    assert scan_network(platform_name="linux") == []


def test_scan_network_passes_timeout_through(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, int] = {}

    def fake_run_ip_neigh(timeout_seconds: int) -> str | None:
        captured["timeout_seconds"] = timeout_seconds
        return None

    monkeypatch.setattr(discovery_module, "_run_ip_neigh", fake_run_ip_neigh)

    scan_network(timeout_seconds=12, platform_name="linux")

    assert captured["timeout_seconds"] == 12


# ---------------------------------------------------------------------------
# 15) Duplicate kayıtların davranışı
# ---------------------------------------------------------------------------


def test_duplicate_ip_and_interface_last_occurrence_wins() -> None:
    raw = (
        "192.168.1.1 dev eth0 lladdr aa:bb:cc:dd:ee:ff STALE\n"
        "192.168.1.1 dev eth0 lladdr aa:bb:cc:dd:ee:ff REACHABLE\n"
    )

    hosts = _parse_ip_neigh_output(raw)

    assert len(hosts) == 1
    assert hosts[0].state == "REACHABLE"


def test_same_ip_different_interface_are_not_duplicates() -> None:
    raw = (
        "192.168.1.1 dev eth0 lladdr aa:bb:cc:dd:ee:ff REACHABLE\n"
        "192.168.1.1 dev wlan0 lladdr aa:bb:cc:dd:ee:ff REACHABLE\n"
    )

    hosts = _parse_ip_neigh_output(raw)

    assert len(hosts) == 2
    assert {h.interface for h in hosts} == {"eth0", "wlan0"}


# ---------------------------------------------------------------------------
# 16) IPv4 / IPv6 ayrımının beklenen davranışı
# ---------------------------------------------------------------------------


def test_ipv6_line_is_parsed_through_same_path() -> None:
    host = _parse_neigh_line("fe80::1 dev eth0 lladdr aa:bb:cc:dd:ee:ff REACHABLE")

    assert host is not None
    assert host.ip == "fe80::1"
    assert host.interface == "eth0"


def test_loopback_address_is_filtered_out() -> None:
    host = _parse_neigh_line("127.0.0.1 dev lo lladdr 00:00:00:00:00:00 PERMANENT")

    assert host is None


def test_ipv6_loopback_is_filtered_out() -> None:
    host = _parse_neigh_line("::1 dev lo PERMANENT")

    assert host is None


def test_multicast_address_is_filtered_out() -> None:
    host = _parse_neigh_line("224.0.0.1 dev eth0 PERMANENT")

    assert host is None


# ---------------------------------------------------------------------------
# MAC normalizasyon yardımcı fonksiyonu
# ---------------------------------------------------------------------------


def test_normalize_discovery_mac_lowercases_and_converts_dashes() -> None:
    assert _normalize_discovery_mac("AA-BB-CC-DD-EE-FF") == "aa:bb:cc:dd:ee:ff"


def test_normalize_discovery_mac_already_lowercase_colon() -> None:
    assert _normalize_discovery_mac("aa:bb:cc:dd:ee:ff") == "aa:bb:cc:dd:ee:ff"

# ---------------------------------------------------------------------------
# v0.4 multi-platform discovery parsers/backends
# ---------------------------------------------------------------------------


def test_parse_windows_neighbors_json() -> None:
    raw = '[{"IPAddress":"192.168.1.1","LinkLayerAddress":"AA-BB-CC-DD-EE-FF","State":"Reachable","InterfaceAlias":"Wi-Fi"}]'
    hosts = discovery_module._parse_windows_neighbors_json(raw)
    assert hosts == [
        DiscoveredHost(
            ip="192.168.1.1",
            interface="Wi-Fi",
            mac="aa:bb:cc:dd:ee:ff",
            state="Reachable",
        )
    ]


def test_parse_windows_arp_fallback() -> None:
    raw = """Interface: 192.168.1.50 --- 0x6
  Internet Address      Physical Address      Type
  192.168.1.1           aa-bb-cc-dd-ee-ff     dynamic
"""
    hosts = discovery_module._parse_windows_arp_output(raw)
    assert len(hosts) == 1
    assert hosts[0].ip == "192.168.1.1"
    assert hosts[0].mac == "aa:bb:cc:dd:ee:ff"


def test_parse_macos_arp_output() -> None:
    raw = "? (192.168.1.1) at aa:bb:cc:dd:ee:ff on en0 ifscope [ethernet]\n"
    hosts = discovery_module._parse_macos_arp_output(raw)
    assert hosts == [
        DiscoveredHost(
            ip="192.168.1.1",
            interface="en0",
            mac="aa:bb:cc:dd:ee:ff",
            state="REACHABLE",
        )
    ]


def test_windows_scan_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        discovery_module,
        "_run_windows_neighbors",
        lambda timeout: '[{"IPAddress":"10.0.0.1","LinkLayerAddress":"11-22-33-44-55-66","State":"Stale","InterfaceAlias":"Ethernet"}]',
    )
    monkeypatch.setattr(discovery_module, "lookup_vendor", lambda mac: None)
    hosts = scan_network(platform_name="win32")
    assert len(hosts) == 1
    assert hosts[0].interface == "Ethernet"


def test_macos_scan_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        discovery_module,
        "_run_macos_arp",
        lambda timeout: "? (10.0.0.1) at 11:22:33:44:55:66 on en0 ifscope [ethernet]\n",
    )
    monkeypatch.setattr(discovery_module, "lookup_vendor", lambda mac: None)
    hosts = scan_network(platform_name="darwin")
    assert len(hosts) == 1
    assert hosts[0].interface == "en0"


def test_windows_neighbor_parser_filters_global_broadcast() -> None:
    raw = '[{"IPAddress":"255.255.255.255","LinkLayerAddress":"ff-ff-ff-ff-ff-ff","State":"Permanent","InterfaceAlias":"Ethernet"}]'
    assert discovery_module._parse_windows_neighbors_json(raw) == []
