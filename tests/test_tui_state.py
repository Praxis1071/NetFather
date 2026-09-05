"""
tui.state için testler.

Bu modül tamamen saf Python'dur (Rich/terminal bağımlılığı yok), bu yüzden
testler doğrudan, hiçbir mock gerekmeden çalışır.
"""

from __future__ import annotations

import datetime as dt

from network.discovery import DiscoveredHost
from tui.state import (
    NAV_ORDER,
    AppState,
    Screen,
    apply_navigation_move,
    move_nav_index,
    record_scan_failure,
    record_scan_result,
    select_current_screen,
)


# ---------------------------------------------------------------------------
# Varsayılan ekran = Overview
# ---------------------------------------------------------------------------


def test_default_screen_is_overview() -> None:
    state = AppState()
    assert state.current_screen == Screen.OVERVIEW


def test_default_nav_index_points_to_overview() -> None:
    state = AppState()
    assert NAV_ORDER[state.nav_index] == Screen.OVERVIEW


def test_nav_order_contains_all_required_screens_in_expected_order() -> None:
    assert list(NAV_ORDER) == [
        Screen.OVERVIEW,
        Screen.DEVICES,
        Screen.NETWORK,
        Screen.DISCOVERY,
        Screen.TOPOLOGY,
        Screen.PROFILES,
        Screen.RULES,
        Screen.MONITOR,
        Screen.EVENTS,
        Screen.CONFIGURATION,
        Screen.LOGS,
    ]


# ---------------------------------------------------------------------------
# Navigasyon
# ---------------------------------------------------------------------------


def test_move_nav_index_down_increments() -> None:
    assert move_nav_index(0, +1, screen_count=8) == 1


def test_move_nav_index_up_decrements() -> None:
    assert move_nav_index(3, -1, screen_count=8) == 2


def test_move_nav_index_wraps_up_from_first() -> None:
    assert move_nav_index(0, -1, screen_count=8) == 7


def test_move_nav_index_wraps_down_from_last() -> None:
    assert move_nav_index(7, +1, screen_count=8) == 0


def test_apply_navigation_move_changes_index_not_current_screen() -> None:
    state = AppState()
    apply_navigation_move(state, +1)

    assert state.nav_index == 1
    # current_screen yalnızca Enter'da (select_current_screen) değişmeli.
    assert state.current_screen == Screen.OVERVIEW


def test_select_current_screen_updates_current_screen_from_nav_index() -> None:
    state = AppState()
    apply_navigation_move(state, +1)  # Devices'e taşı
    apply_navigation_move(state, +1)  # Network'e taşı

    select_current_screen(state)

    assert state.current_screen == Screen.NETWORK


def test_navigation_full_cycle_wraps_back_to_start() -> None:
    state = AppState()
    for _ in range(len(NAV_ORDER)):
        apply_navigation_move(state, +1)

    assert state.nav_index == 0


# ---------------------------------------------------------------------------
# Tarama durumu kaydı
# ---------------------------------------------------------------------------


def test_record_scan_result_stores_hosts_and_clears_error() -> None:
    state = AppState()
    state.last_scan_error = "önceki hata"
    hosts = [DiscoveredHost(ip="192.168.1.1", interface="eth0", mac="aa:bb:cc:dd:ee:ff", state="REACHABLE")]
    now = dt.datetime(2026, 1, 1, 12, 0, 0)

    record_scan_result(state, hosts, now=now)

    assert state.last_scan_hosts == hosts
    assert state.last_scan_time == now
    assert state.last_scan_error is None


def test_record_scan_failure_stores_message_without_clearing_previous_hosts() -> None:
    state = AppState()
    previous_hosts = [DiscoveredHost(ip="10.0.0.1")]
    state.last_scan_hosts = previous_hosts

    record_scan_failure(state, "Hiçbir cihaz bulunamadı.")

    assert state.last_scan_error == "Hiçbir cihaz bulunamadı."
    # Önceki başarılı tarama sonucu, yeni bir başarısızlıkla silinmemeli
    # (kullanıcı en son bilinen iyi veriyi görmeye devam edebilmeli).
    assert state.last_scan_hosts == previous_hosts
