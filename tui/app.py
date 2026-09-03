"""
TUI ana döngüsü.

Bu modül, portable terminal girdi katmanı, Rich `Live` ile yeniden çizim
ve ekranlar arası dispatch mantığını içerir. Hiçbir iş mantığı burada
YOKTUR — yalnızca `tui/data.py`, `tui/render.py` ve `tui/terminal.py`'yi
çağırır. POSIX terminal ayrıntıları capability-aware bir katmanda tutulur.
"""

from __future__ import annotations

import contextlib
import os
import signal
import sys
from typing import IO, Iterator

from rich.console import Console
from rich.live import Live

from cli.output import print_error, print_info
from core.config import Config
from core.database import Database
from core.logger import get_logger
from tui.data import (
    get_config_display_rows,
    get_discovery_data,
    get_network_data,
    get_profiles,
    get_rules,
    get_overview_data,
    get_recent_log_lines,
    get_registered_devices,
    invalidate_network_status_cache,
    trigger_scan,
    sync_known_discovered,
)
from tui.render import (
    build_layout,
    render_active_view,
    render_configuration_screen,
    render_devices_screen,
    render_discovery_screen,
    render_footer,
    render_header,
    render_logs_screen,
    render_navigation,
    render_network_screen,
    render_profiles_screen,
    render_rules_screen,
    render_overview_screen,
    render_overview_strip,
    render_placeholder_screen,
    render_terminal_too_small,
)
from tui.state import (
    AppState,
    Screen,
    apply_navigation_move,
    record_scan_failure,
    record_scan_result,
    NAV_ORDER,
    select_current_screen,
)
from tui.terminal import (
    TerminalMode,
    detect_terminal_capabilities,
    read_key,
    terminal_input_mode,
)

log = get_logger("tui.app")

_KEY_READ_TIMEOUT_SECONDS = 0.5
_ESCAPE_SEQUENCE_TIMEOUT_SECONDS = 0.05

# Discovery sonuçlarını gösteren, dolayısıyla 'r' ile gerçek bir tarama
# tetikleyebilecek ekranlar. Diğer ekranlarda 'r' yalnızca önbelleği
# temizleyip yeniden çizer; her yerde otomatik/agresif tarama yapılmaz.
_SCREENS_THAT_RESCAN_ON_REFRESH = (Screen.DISCOVERY, Screen.DEVICES)


@contextlib.contextmanager
def _reliable_terminal_size() -> Iterator[None]:
    """
    Rich'in `Console.size`'ının GERÇEK terminal boyutunu kullanmasını garanti eder.

    Kök neden: Rich'in `Console.size` özelliği, gerçek terminal boyutunu
    (ioctl/`TIOCGWINSZ`) sormadan ÖNCE `COLUMNS`/`LINES` ortam
    değişkenlerini kontrol eder ve varsa onları önceliklendirir. Bazı
    kabuklar (shell) bu değişkenleri export eder; bu değerler terminal
    yeniden boyutlandırıldığında veya farklı bir pencere/sekmeden
    başlatıldığında GÜNCELLENMEYEBİLİR (bayat kalabilir). Bayat bir
    COLUMNS/LINES varsa, TUI gerçek terminalden FARKLI bir boyutta
    render edilir — içerik gerçek terminale göre kayar/kırpılır (ör.
    header'ın görünmemesi, yalnızca alt kısmın görünmesi gibi bir
    "scroll" belirtisi).

    Bu context manager, TUI çalışırken bu iki değişkeni geçici olarak
    kaldırır (Rich'in güvenilir, dinamik ioctl tabanlı gerçek boyut
    tespitine düşmesi için) ve çıkışta orijinal ortamı aynen geri
    yükler.
    """
    saved: dict[str, str] = {}
    for key in ("COLUMNS", "LINES"):
        if key in os.environ:
            saved[key] = os.environ.pop(key)
    try:
        yield
    finally:
        os.environ.update(saved)


@contextlib.contextmanager
def _raw_terminal(stream: IO[str]) -> Iterator[None]:
    """Compatibility wrapper around the safer cbreak terminal mode."""
    with terminal_input_mode(stream):
        yield


def _read_key(timeout: float = _KEY_READ_TIMEOUT_SECONDS) -> str:
    """Read one normalized key event from the terminal descriptor."""
    return read_key(
        sys.stdin,
        timeout=timeout,
        escape_timeout=_ESCAPE_SEQUENCE_TIMEOUT_SECONDS,
    )

def _build_active_view_content(state: AppState, config: Config, db: Database, overview_data):
    """Seçili ekrana göre Active View panelinin içeriğini oluşturur."""
    if state.current_screen == Screen.OVERVIEW:
        # overview_data zaten _render_full_page tarafından hesaplandı;
        # burada tekrar hesaplamıyoruz (gereksiz DB sorgusu olmasın diye).
        return render_overview_screen(overview_data)

    if state.current_screen == Screen.NETWORK:
        return render_network_screen(get_network_data(state))

    if state.current_screen == Screen.DISCOVERY:
        return render_discovery_screen(get_discovery_data(state))

    if state.current_screen == Screen.DEVICES:
        devices, error = get_registered_devices(db)
        return render_devices_screen(devices, error, get_discovery_data(state))

    if state.current_screen == Screen.PROFILES:
        profiles, error = get_profiles(db)
        return render_profiles_screen(profiles, error)

    if state.current_screen == Screen.RULES:
        rules, error = get_rules(db)
        return render_rules_screen(rules, error)

    if state.current_screen == Screen.CONFIGURATION:
        return render_configuration_screen(get_config_display_rows(config))

    if state.current_screen == Screen.LOGS:
        lines, message = get_recent_log_lines(config)
        return render_logs_screen(lines, message)

    if state.current_screen == Screen.MONITOR:
        return render_placeholder_screen("Monitor functionality is planned for a future phase.")

    # Buraya normalde ulaşılmaz (tüm Screen değerleri yukarıda ele alındı).
    return render_placeholder_screen("Unknown screen.")


def _render_full_page(state: AppState, config: Config, db: Database, console: Console):
    """Build a terminal-size-aware full page."""
    width, height = console.size
    if width < 44 or height < 14:
        return render_terminal_too_small(width, height)

    compact = width < 100 or height < 30
    overview_data = get_overview_data(config, db, state)

    if not overview_data.database_ok:
        system_ok: bool | None = False
    elif overview_data.network_status_known:
        system_ok = True
    else:
        system_ok = None

    active_view_content = _build_active_view_content(state, config, db, overview_data)

    return build_layout(
        console,
        header=render_header(system_ok),
        overview_strip=render_overview_strip(overview_data, compact=compact),
        navigation=render_navigation(state, compact=compact),
        active_view=render_active_view(state, active_view_content),
        footer=render_footer(state.status_message, compact=compact),
        compact=compact,
    )

def _handle_key(key: str, state: AppState, config: Config, db: Database | None = None) -> None:
    """Tek bir klavye olayını duruma uygular. Rich/terminal ile ilgili hiçbir şey yapmaz."""
    if key == "QUIT":
        state.should_quit = True
    elif key == "UP":
        apply_navigation_move(state, -1)
    elif key == "DOWN":
        apply_navigation_move(state, +1)
    elif key == "HOME":
        state.nav_index = 0
    elif key == "END":
        state.nav_index = len(NAV_ORDER) - 1
    elif key == "ENTER":
        select_current_screen(state)
    elif key == "REFRESH":
        invalidate_network_status_cache(state)
        if state.current_screen in _SCREENS_THAT_RESCAN_ON_REFRESH:
            hosts, error = trigger_scan(config)
            if error:
                record_scan_failure(state, error)
                state.status_message = error
            else:
                record_scan_result(state, hosts)
                state.status_message = f"{len(hosts)} host bulundu."
    elif key == "SYNC":
        if db is None:
            state.status_message = "Database hazır değil."
        elif state.current_screen not in _SCREENS_THAT_RESCAN_ON_REFRESH:
            state.status_message = "Sync yalnız Discovery/Devices ekranında kullanılabilir."
        else:
            updated, error = sync_known_discovered(db, state)
            state.status_message = error or f"{updated} kayıtlı cihaz güncellendi."


def _install_resize_handler(resize_state: dict[str, bool]):
    """Install SIGWINCH when possible; return the previous handler."""
    if not hasattr(signal, "SIGWINCH"):
        return None

    def _on_resize(signum: int, frame: object) -> None:
        resize_state["pending"] = True

    try:
        return signal.signal(signal.SIGWINCH, _on_resize)
    except (ValueError, OSError):
        # signal.signal() is only legal in the main thread.  Embedders may
        # launch NetFather elsewhere; the TUI must still remain usable.
        return None


def _restore_resize_handler(previous_handler) -> None:
    if previous_handler is None or not hasattr(signal, "SIGWINCH"):
        return
    try:
        signal.signal(signal.SIGWINCH, previous_handler)
    except (ValueError, OSError):
        pass


def _plain_command_to_key(command: str) -> str:
    normalized = command.strip()
    aliases = {
        "": "",
        "j": "DOWN",
        "down": "DOWN",
        "k": "UP",
        "up": "UP",
        "g": "HOME",
        "G": "END",
        "home": "HOME",
        "end": "END",
        "enter": "ENTER",
        "open": "ENTER",
        "r": "REFRESH",
        "refresh": "REFRESH",
        "s": "SYNC",
        "sync": "SYNC",
        "q": "QUIT",
        "quit": "QUIT",
        "exit": "QUIT",
    }
    return aliases.get(normalized, "")


def _run_plain_tui(config: Config, db: Database, console: Console) -> None:
    """Line-oriented fallback for TERM=dumb and other limited terminals."""
    state = AppState()
    state.status_message = "Limited terminal detected: plain compatibility mode."

    while not state.should_quit:
        console.print(_render_full_page(state, config, db, console))
        try:
            command = input("netfather [j/k, enter, r, s, q]> ")
        except (EOFError, KeyboardInterrupt):
            break
        key = _plain_command_to_key(command)
        if key:
            _handle_key(key, state, config, db)


def _run_live_tui(
    config: Config,
    db: Database,
    console: Console,
    mode: TerminalMode,
) -> None:
    state = AppState()
    resize_state = {"pending": False}
    previous_handler = _install_resize_handler(resize_state)
    fullscreen = mode is TerminalMode.FULLSCREEN

    try:
        with _reliable_terminal_size(), _raw_terminal(sys.stdin):
            with Live(
                console=console,
                screen=fullscreen,
                auto_refresh=False,
                transient=fullscreen,
                vertical_overflow="crop",
            ) as live:
                live.update(_render_full_page(state, config, db, console), refresh=True)
                while not state.should_quit:
                    try:
                        key = _read_key()
                        needs_redraw = False

                        if resize_state["pending"]:
                            resize_state["pending"] = False
                            needs_redraw = True
                        if key:
                            _handle_key(key, state, config, db)
                            needs_redraw = True

                        if needs_redraw:
                            live.update(_render_full_page(state, config, db, console), refresh=True)
                    except Exception as exc:  # noqa: BLE001 - TUI should survive view errors
                        log.exception("TUI döngüsünde beklenmeyen hata: %s", exc)
                        state.status_message = (
                            "Beklenmeyen bir hata oluştu (log dosyasına kaydedildi)."
                        )
                        live.update(_render_full_page(state, config, db, console), refresh=True)
    finally:
        _restore_resize_handler(previous_handler)


def run_tui(config: Config, db: Database, mode: str | TerminalMode = TerminalMode.AUTO) -> None:
    """Start NetFather's terminal UI using a capability-aware safe mode."""
    if not sys.platform.startswith("linux"):
        print_error("NetFather TUI şu anda Linux gerektirir.")
        return

    capabilities = detect_terminal_capabilities(
        sys.stdin,
        sys.stdout,
        requested_mode=mode,
    )
    if not capabilities.interactive:
        print_error("NetFather TUI interaktif bir terminal gerektirir.")
        print_info("Komut satırı kullanımı için: netfather --help")
        return

    if capabilities.reason:
        log.info(
            "Terminal compatibility mode: TERM=%s mode=%s reason=%s",
            capabilities.term or "<unset>",
            capabilities.mode.value,
            capabilities.reason,
        )

    try:
        # Console must be constructed AFTER stale COLUMNS/LINES are removed.
        # Rich may cache those environment values during initialization.
        with _reliable_terminal_size():
            console = Console()
            if capabilities.mode is TerminalMode.PLAIN:
                _run_plain_tui(config, db, console)
            else:
                _run_live_tui(config, db, console, capabilities.mode)
    except KeyboardInterrupt:
        pass
    except Exception as exc:  # noqa: BLE001 - terminal setup must not crash CLI
        log.exception("TUI başlatılamadı: %s", exc)
        print_error("TUI başlatılamadı. Ayrıntılar log dosyasına kaydedildi.")
        if capabilities.mode is TerminalMode.FULLSCREEN:
            print_info("Uyumluluk modu için deneyin: netfather tui --mode inline")
