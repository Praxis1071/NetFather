"""
TUI ana döngüsü.

Bu modül, klavye okuma (ham/raw terminal modu), Rich `Live` ile yeniden
çizim ve ekranlar arası dispatch mantığını içerir. Hiçbir iş mantığı
burada YOKTUR — yalnızca `tui/data.py` ve `tui/render.py`'yi çağırır.

Linux'a özgüdür (`termios`/`tty`); bu, projenin hedef platformuyla
(CachyOS/Arch/Linux) tutarlıdır.
"""

from __future__ import annotations

import contextlib
import os
import select
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
)
from tui.state import (
    AppState,
    Screen,
    apply_navigation_move,
    record_scan_failure,
    record_scan_result,
    select_current_screen,
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
    """
    Terminali ham (raw) moda alır ve çıkışta (hata olsa bile) eski ayarlara geri döndürür.

    Yalnızca Linux/Unix terminallerinde çalışır (`termios`/`tty` stdlib).
    """
    import termios
    import tty

    fd = stream.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        yield
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def _wait_for_input(timeout: float) -> bool:
    """`timeout` saniye içinde stdin'den okunabilir veri gelip gelmediğini döndürür."""
    ready, _, _ = select.select([sys.stdin], [], [], timeout)
    return bool(ready)


def _read_key(timeout: float = _KEY_READ_TIMEOUT_SECONDS) -> str:
    """
    Tek bir klavye olayını okur ve normalize edilmiş bir sembolik isim döndürür.

    Dönüş değerleri: "UP", "DOWN", "ENTER", "QUIT", "REFRESH",
    "SYNC" ya da zaman aşımı/tanınmayan tuş için "" (boş string).
    """
    if not _wait_for_input(timeout):
        return ""

    ch = sys.stdin.read(1)

    if ch == "\x03":
        # Ctrl+C. tty.setraw() termios LFLAG'inden ISIG'i de kapatır, bu
        # yüzden ham modda Ctrl+C artık bir SIGINT/KeyboardInterrupt
        # ÜRETMEZ — yalnızca ham 0x03 baytı olarak okunur. Bunu açıkça
        # QUIT olarak ele almazsak Ctrl+C'nin TUI içinde hiçbir etkisi
        # olmaz.
        return "QUIT"

    if ch == "\x1b":
        # Olası bir ANSI escape dizisi (ok tuşları: ESC [ A / ESC [ B).
        if _wait_for_input(_ESCAPE_SEQUENCE_TIMEOUT_SECONDS):
            rest = sys.stdin.read(2)
            if rest == "[A":
                return "UP"
            if rest == "[B":
                return "DOWN"
        return ""  # yalnızca ESC ya da tanınmayan dizi: yok say

    if ch in ("\r", "\n"):
        return "ENTER"
    if ch in ("q", "Q"):
        return "QUIT"
    if ch in ("r", "R"):
        return "REFRESH"
    if ch in ("s", "S"):
        return "SYNC"
    return ""


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
    """Tüm sayfayı (header, overview şeridi, navigation, active view, footer) oluşturur."""
    overview_data = get_overview_data(config, db, state)

    if not overview_data.database_ok:
        system_ok: bool | None = False
    elif overview_data.network_status_known:
        system_ok = True
    else:
        # Database çalışıyor ama ağ tespiti şu an mümkün değil (ör. offline
        # makine) — bu kesin bir "sorun" değil, bu yüzden "bilinmiyor".
        system_ok = None

    active_view_content = _build_active_view_content(state, config, db, overview_data)

    return build_layout(
        console,
        header=render_header(system_ok),
        overview_strip=render_overview_strip(overview_data),
        navigation=render_navigation(state),
        active_view=render_active_view(state, active_view_content),
        footer=render_footer(state.status_message),
    )


def _handle_key(key: str, state: AppState, config: Config, db: Database | None = None) -> None:
    """Tek bir klavye olayını duruma uygular. Rich/terminal ile ilgili hiçbir şey yapmaz."""
    if key == "QUIT":
        state.should_quit = True
    elif key == "UP":
        apply_navigation_move(state, -1)
    elif key == "DOWN":
        apply_navigation_move(state, +1)
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


def run_tui(config: Config, db: Database) -> None:
    """
    NetFather TUI'sini başlatır.

    `python -m netfather` (parametresiz) çağrıldığında `cli/commands.py`
    tarafından çağrılır. TUI mevcut CLI ile aynı `config`/`db` nesnelerini
    kullanır; ayrı bir bootstrap yapmaz.

    Bu fonksiyon hiçbir şekilde exception ile sonlanmaz: interaktif olmayan
    bir terminalde çağrılırsa, ya da döngü içinde beklenmeyen bir hata
    oluşursa, kullanıcıya anlaşılır bir mesaj gösterip zarifçe döner.
    Terminal, her koşulda (Ctrl+C dahil) eski durumuna geri yüklenir.
    """
    if not sys.platform.startswith("linux"):
        print_error("NetFather TUI şu anda Linux terminali gerektirir.")
        return
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print_error("NetFather TUI interaktif bir terminal gerektirir.")
        print_info("Komut satırı kullanımı için: netfather --help")
        return

    # Live ve raw-terminal ile ilgili importlar modül üstünde zaten yapıldı;
    # burada yalnızca gerçek terminal etkileşimi başlıyor.
    state = AppState()
    console = Console()

    # Terminal yeniden boyutlandırıldığında (SIGWINCH) bir sonraki
    # klavye olayını beklemeden hemen yeniden çizim yapılabilmesi için.
    # Bu bir thread DEĞİLDİR — sinyal işleyicisi ana thread üzerinde,
    # normal Python bytecode'ları arasında asenkron olarak çağrılır;
    # dolayısıyla "gereksiz concurrency" yaratmaz, yalnızca bir bayrak
    # (flag) ayarlar. Gerçek yeniden çizim, ana döngüde (aşağıda)
    # senkron şekilde yapılır.
    resize_state = {"pending": False}

    def _on_resize(signum: int, frame: object) -> None:
        resize_state["pending"] = True

    has_sigwinch = hasattr(signal, "SIGWINCH")
    previous_handler = signal.signal(signal.SIGWINCH, _on_resize) if has_sigwinch else None

    try:
        with _reliable_terminal_size(), _raw_terminal(sys.stdin):
            with Live(console=console, screen=True, auto_refresh=False, transient=True) as live:
                # ÖNEMLİ: Live `auto_refresh=False` ile oluşturuldu (arka
                # planda gereksiz bir yenileme thread'i açmamak için — bkz.
                # modül docstring'i, "CPU'yu gereksiz tüketmeme" hedefi).
                # Bu nedenle her `update()` çağrısında `refresh=True`
                # AÇIKÇA geçirilmelidir; aksi halde Live'ın dahili tamponu
                # güncellenir ama ekrana HİÇBİR ZAMAN gerçekten çizilmez
                # (Rich'in `Live.update()` varsayılanı `refresh=False`'tur).
                # Bu satırın unutulması "neredeyse boş ekran" sorununun
                # doğrudan sebebiydi.
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
                    except Exception as exc:  # noqa: BLE001 - TUI çökmemeli
                        log.exception("TUI döngüsünde beklenmeyen hata: %s", exc)
                        state.status_message = "Beklenmeyen bir hata oluştu (log dosyasına kaydedildi)."
                        live.update(_render_full_page(state, config, db, console), refresh=True)
    except KeyboardInterrupt:
        # Terminal, _raw_terminal'in finally bloğu tarafından zaten restore edilir.
        pass
    except Exception as exc:  # noqa: BLE001 - terminal setup da uygulamayı düşürmemeli
        log.exception("TUI başlatılamadı: %s", exc)
        print_error("TUI başlatılamadı. Ayrıntılar log dosyasına kaydedildi.")
    finally:
        if has_sigwinch and previous_handler is not None:
            signal.signal(signal.SIGWINCH, previous_handler)
