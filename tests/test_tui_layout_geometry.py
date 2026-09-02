"""
tui/render.py'nin Layout geometri hesaplarını doğrulayan testler.

Bu testler GERÇEK Rich render motorunu kullanır (`Console(file=io.StringIO())`
ile tty'siz/headless), böylece "bu panel şu kadar satır tutar" iddiaları
sahte/mock bir render fonksiyonuyla değil, Rich'in kendi border/padding/
içerik hesaplama mantığıyla doğrulanır.

Bu dosya, FAZ2.3 TUI'sinde gerçek terminalde tespit edilen bir kök neden
hatasının (Overview panelinin Layout'a sabit `size=6` ile verilmesine
rağmen gerçekte 7 satıra ihtiyaç duyması) regresyon testidir.
"""

from __future__ import annotations

import io

import pytest
from rich.console import Console

from tui.data import OverviewData
from tui.render import (
    _measure_renderable_height,
    build_layout,
    render_active_view,
    render_footer,
    render_header,
    render_navigation,
    render_overview_strip,
    render_placeholder_screen,
)
from tui.state import NAV_ORDER, AppState

# Doküman'da açıkça istenen, TUI'nin makul davranması gereken terminal
# boyutları (genişlik x yükseklik).
_TARGET_TERMINAL_SIZES = [(120, 30), (140, 35), (161, 37), (180, 45)]
_TARGET_WIDTHS = [size[0] for size in _TARGET_TERMINAL_SIZES]


def _headless_console(width: int = 161, height: int = 37) -> Console:
    """tty gerektirmeyen, sabit boyutlu bir Console döndürür (yalnızca ölçüm/test amaçlı)."""
    return Console(file=io.StringIO(), width=width, height=height, force_terminal=True)


# ---------------------------------------------------------------------------
# Tekil panel yükseklik ölçümleri (gerçek Rich render motoruyla)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("width", _TARGET_WIDTHS)
def test_header_measures_to_exactly_three_lines(width: int) -> None:
    """Header: 2 border + 0 padding + 1 içerik satırı = 3."""
    console = _headless_console(width=width)
    header = render_header(True)

    assert _measure_renderable_height(header, console, width) == 3


@pytest.mark.parametrize("width", _TARGET_WIDTHS)
def test_overview_strip_measures_to_exactly_seven_lines(width: int) -> None:
    """
    REGRESYON TESTİ (kök neden): Overview paneli `padding=(1, 2)` (dikey=1)
    kullanır: 2 border + 2 dikey padding (üst+alt) + 3 içerik satırı = 7.

    Önceki kodda Layout'a bunun için sabit `size=6` verilmişti — 1 satır
    eksikti ve bu, gerçek terminalde Overview'ün alt kısmının (ya da
    kümülatif olarak tüm sayfanın) kırpılmasına katkıda bulunuyordu. Artık
    bu değer `_measure_renderable_height()` ile HESAPLANIYOR; bu test o
    hesaplamanın gerçekten 7 verdiğini doğrular.
    """
    console = _headless_console(width=width)
    strip = render_overview_strip(OverviewData())

    assert _measure_renderable_height(strip, console, width) == 7


@pytest.mark.parametrize("width", _TARGET_WIDTHS)
def test_footer_measures_to_exactly_three_lines(width: int) -> None:
    """Footer: 2 border + 0 padding + 1 içerik satırı = 3."""
    console = _headless_console(width=width)
    footer = render_footer()

    assert _measure_renderable_height(footer, console, width) == 3


@pytest.mark.parametrize("width", _TARGET_WIDTHS)
def test_navigation_panel_natural_height_matches_expected_formula(width: int) -> None:
    """Navigation: 2 border + 2 dikey padding (padding=(1,1)) + 8 nav öğesi = 12."""
    console = _headless_console(width=width)
    state = AppState()
    nav = render_navigation(state)

    expected = 2 + 2 + len(NAV_ORDER)
    assert _measure_renderable_height(nav, console, width) == expected


def test_measure_renderable_height_falls_back_on_invalid_width() -> None:
    """width=0 gibi dejenere bir değer verilirse ölçüm fonksiyonu çökmemeli."""
    console = _headless_console(width=80)
    header = render_header(None)

    height = _measure_renderable_height(header, console, width=0)

    assert height == 3  # makul bir varsayılan genişlikle ölçüldü, çökmedi


# ---------------------------------------------------------------------------
# build_layout(): sabit bölgelerin ölçülen değerlerle eşleştiği doğrulanır
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cols,rows", _TARGET_TERMINAL_SIZES)
def test_build_layout_fixed_regions_match_measured_heights(cols: int, rows: int) -> None:
    """
    `build_layout()`'un header/overview/footer için Layout'a verdiği
    `size=` değerlerinin, panellerin GERÇEKTEN ölçülen doğal
    yükseklikleriyle birebir eşleştiğini, doküman'ın istediği dört farklı
    terminal boyutunun (120x30, 140x35, 161x37, 180x45) hepsinde doğrular.
    """
    console = _headless_console(width=cols, height=rows)
    state = AppState()

    layout = build_layout(
        console,
        header=render_header(True),
        overview_strip=render_overview_strip(OverviewData()),
        navigation=render_navigation(state),
        active_view=render_active_view(state, render_placeholder_screen("x")),
        footer=render_footer(),
    )

    assert layout["header"].size == 3
    assert layout["overview"].size == 7
    assert layout["footer"].size == 3


@pytest.mark.parametrize("cols,rows", _TARGET_TERMINAL_SIZES)
def test_build_layout_body_has_enough_room_for_navigation(cols: int, rows: int) -> None:
    """
    Sabit bölgeler (header=3 + overview=7 + footer=3 = 13 satır)
    çıkarıldıktan sonra "body" için kalan alanın, Navigation panelinin
    doğal yüksekliğini (12 satır) karşılayacak kadar olduğunu doğrular.

    Bu, gerçek terminalde bildirilen "Navigation'ın yalnızca çok küçük/
    belirsiz bir kısmı görünüyor" belirtisine karşı bir güvence testidir:
    eğer bu test geçiyorsa, hedeflenen dört terminal boyutunun hiçbirinde
    body alanı Navigation'ı kırpacak kadar küçük DEĞİLDİR.
    """
    fixed_total = 3 + 7 + 3  # header + overview + footer (ölçülmüş değerler)
    remaining_body_height = rows - fixed_total
    nav_natural_height = 2 + 2 + len(NAV_ORDER)  # border + padding + 8 öğe

    assert remaining_body_height > 0, (
        f"{cols}x{rows} terminalinde body için hiç alan kalmıyor "
        f"(sabit bölgeler {fixed_total} satır tüketiyor)"
    )
    assert remaining_body_height >= nav_natural_height, (
        f"{cols}x{rows} terminalinde Navigation paneli ({nav_natural_height} satır) "
        f"kalan body alanına ({remaining_body_height} satır) sığmıyor"
    )


def test_build_layout_never_raises_at_very_small_terminal_size() -> None:
    """
    Uç durum: çok küçük bir terminalde (ör. 40x10) bile `build_layout()`
    exception fırlatmamalı — okunabilirlik bozulabilir ama TUI çökmemeli.
    """
    console = _headless_console(width=40, height=10)
    state = AppState()

    layout = build_layout(
        console,
        header=render_header(True),
        overview_strip=render_overview_strip(OverviewData()),
        navigation=render_navigation(state),
        active_view=render_active_view(state, render_placeholder_screen("x")),
        footer=render_footer(),
    )

    assert layout is not None
