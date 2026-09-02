"""
TUI uygulama durumu.

Bu modül kasıtlı olarak Rich'ten bağımsızdır: navigasyon ve durum mantığı
tamamen saf Python'dur, böylece gerçek bir terminal veya Rich kurulumu
gerekmeden test edilebilir.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from enum import Enum

from network.discovery import DiscoveredHost
from network.interface import NetworkStatus


class Screen(str, Enum):
    """Sol navigasyon panelindeki ekranlar, gösterim sırasıyla."""

    OVERVIEW = "Overview"
    DEVICES = "Devices"
    NETWORK = "Network"
    DISCOVERY = "Discovery"
    PROFILES = "Profiles"
    RULES = "Rules"
    MONITOR = "Monitor"
    CONFIGURATION = "Configuration"
    LOGS = "Logs"


# Navigasyon sırası; Screen enum tanım sırasıyla aynı, ama bağımsız bir
# liste olarak tutuluyor ki nav_index <-> Screen dönüşümü tek bir yerde
# (bu modülde) net şekilde tanımlı olsun.
NAV_ORDER: tuple[Screen, ...] = tuple(Screen)

DEFAULT_SCREEN_INDEX = NAV_ORDER.index(Screen.OVERVIEW)


@dataclass
class AppState:
    """
    TUI'nin oturum boyunca tuttuğu durum.

    Discovery sonuçları burada yalnızca **bellek içi, oturuma özel bir
    önbellek** olarak tutulur; hiçbir şekilde veritabanına yazılmaz
    (discovery/persistence ayrımı korunuyor). Uygulama kapandığında kaybolur.
    """

    nav_index: int = DEFAULT_SCREEN_INDEX
    current_screen: Screen = Screen.OVERVIEW

    last_scan_hosts: list[DiscoveredHost] = field(default_factory=list)
    last_scan_time: dt.datetime | None = None
    last_scan_error: str | None = None

    # `network.interface.get_network_status()` bir subprocess çağrısı
    # içerir; her render döngüsünde (ör. her ok tuşu basışında) yeniden
    # çalıştırmak UI'yi gereksiz yere yavaşlatır/dondurabilir. Bu yüzden
    # sonucu kısa süreliğine önbelleğe alıyoruz (bkz. tui/data.py).
    cached_network_status: NetworkStatus | None = None
    network_status_fetched_at: dt.datetime | None = None

    # Footer/durum çubuğunda kısa süreliğine gösterilecek bilgi mesajı
    # (ör. "Scanning..." veya bir hata özeti).
    status_message: str | None = None

    should_quit: bool = False


def move_nav_index(current_index: int, delta: int, screen_count: int) -> int:
    """
    Navigasyon seçim indeksini `delta` kadar kaydırır (döngüsel/wrap-around).

    Saf bir fonksiyondur; hiçbir dış durumu değiştirmez, terminal veya Rich
    gerektirmez.

    Args:
        current_index: Şu anki seçili nav indeksi.
        delta: +1 (aşağı) veya -1 (yukarı).
        screen_count: Toplam ekran sayısı (0'dan büyük olmalı).

    Returns:
        Yeni, [0, screen_count) aralığına sarmalanmış indeks.
    """
    if screen_count <= 0:
        return 0
    return (current_index + delta) % screen_count


def apply_navigation_move(state: AppState, delta: int) -> AppState:
    """`state.nav_index`'i kaydırır; `current_screen`'i değiştirmez (Enter'a kadar)."""
    state.nav_index = move_nav_index(state.nav_index, delta, len(NAV_ORDER))
    return state


def select_current_screen(state: AppState) -> AppState:
    """`nav_index`'teki ekranı `current_screen` yapar (Enter tuşu davranışı)."""
    state.current_screen = NAV_ORDER[state.nav_index]
    return state


def record_scan_result(
    state: AppState, hosts: list[DiscoveredHost], now: dt.datetime | None = None
) -> AppState:
    """Başarılı bir taramanın sonucunu duruma (yalnızca bellekte) kaydeder."""
    state.last_scan_hosts = hosts
    state.last_scan_time = now or dt.datetime.now()
    state.last_scan_error = None
    return state


def record_scan_failure(state: AppState, message: str) -> AppState:
    """Başarısız bir tarama denemesini duruma kaydeder (crash yerine)."""
    state.last_scan_error = message
    return state
