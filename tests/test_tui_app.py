"""
tui.app için testler.

`_handle_key` Rich/terminal'den bağımsız, saf durum-geçiş mantığıdır ve
doğrudan test edilir (mevcut projede `_parse_neigh_line`,
`_run_ip_route_get` gibi private fonksiyonların doğrudan test edilmesiyle
aynı üslup). Gerçek klavye okuma (`_read_key`) ve tam etkileşimli döngü
(`run_tui`'nin ana while bloğu) gerçek bir terminal/tty gerektirdiği için
bu dosyada test edilmez — yalnızca `run_tui`'nin tty olmayan bir ortamda
çökmeden zarifçe döndüğü doğrulanır (bkz. test_run_tui_without_tty...).
"""

from __future__ import annotations

import contextlib

import pytest

import tui.app as tui_app
from network.discovery import DiscoveredHost
from tui.state import AppState, Screen


@pytest.fixture
def config(tmp_path, monkeypatch: pytest.MonkeyPatch):
    import core.config as config_module
    from core.config import load_config

    monkeypatch.setattr(config_module, "DEFAULT_DATA_DIR", tmp_path / "data")
    return load_config(config_path=tmp_path / "config.toml")


# ---------------------------------------------------------------------------
# _handle_key: navigasyon ve seçim
# ---------------------------------------------------------------------------


def test_handle_key_quit_sets_should_quit(config) -> None:
    state = AppState()
    tui_app._handle_key("QUIT", state, config)
    assert state.should_quit is True


def test_handle_key_up_moves_nav_index_only(config) -> None:
    state = AppState()
    tui_app._handle_key("DOWN", state, config)
    tui_app._handle_key("UP", state, config)

    assert state.nav_index == 0
    assert state.current_screen == Screen.OVERVIEW  # Enter'a kadar değişmez


def test_handle_key_enter_selects_current_screen(config) -> None:
    state = AppState()
    tui_app._handle_key("DOWN", state, config)  # -> Devices
    tui_app._handle_key("ENTER", state, config)

    assert state.current_screen == Screen.DEVICES


def test_handle_key_unknown_key_is_noop(config) -> None:
    state = AppState()
    before = (state.nav_index, state.current_screen, state.should_quit)

    tui_app._handle_key("", state, config)

    after = (state.nav_index, state.current_screen, state.should_quit)
    assert before == after


# ---------------------------------------------------------------------------
# _handle_key: REFRESH — yalnızca Discovery/Devices ekranlarında tarama tetikler
# ---------------------------------------------------------------------------


def test_handle_key_refresh_on_discovery_triggers_scan(
    config, monkeypatch: pytest.MonkeyPatch
) -> None:
    expected_hosts = [DiscoveredHost(ip="192.168.1.1")]
    monkeypatch.setattr(tui_app, "trigger_scan", lambda cfg: (expected_hosts, None))

    state = AppState()
    state.current_screen = Screen.DISCOVERY

    tui_app._handle_key("REFRESH", state, config)

    assert state.last_scan_hosts == expected_hosts
    assert state.last_scan_error is None


def test_handle_key_refresh_on_devices_triggers_scan(
    config, monkeypatch: pytest.MonkeyPatch
) -> None:
    expected_hosts = [DiscoveredHost(ip="10.0.0.5")]
    monkeypatch.setattr(tui_app, "trigger_scan", lambda cfg: (expected_hosts, None))

    state = AppState()
    state.current_screen = Screen.DEVICES

    tui_app._handle_key("REFRESH", state, config)

    assert state.last_scan_hosts == expected_hosts


def test_handle_key_refresh_on_configuration_does_not_trigger_scan(
    config, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_if_called(cfg):
        raise AssertionError("Configuration ekranında refresh tarama TETİKLEMEMELİ")

    monkeypatch.setattr(tui_app, "trigger_scan", fail_if_called)

    state = AppState()
    state.current_screen = Screen.CONFIGURATION

    tui_app._handle_key("REFRESH", state, config)  # exception fırlatmamalı


def test_handle_key_refresh_records_failure_without_crashing(
    config, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tui_app, "trigger_scan", lambda cfg: ([], "Hiçbir cihaz bulunamadı."))

    state = AppState()
    state.current_screen = Screen.DISCOVERY

    tui_app._handle_key("REFRESH", state, config)

    assert state.last_scan_error == "Hiçbir cihaz bulunamadı."


def test_handle_key_refresh_invalidates_network_cache(
    config, monkeypatch: pytest.MonkeyPatch
) -> None:
    invalidated = {"called": False}

    def fake_invalidate(state):
        invalidated["called"] = True

    monkeypatch.setattr(tui_app, "invalidate_network_status_cache", fake_invalidate)
    monkeypatch.setattr(tui_app, "trigger_scan", lambda cfg: ([], "Hiçbir cihaz bulunamadı."))

    state = AppState()
    tui_app._handle_key("REFRESH", state, config)

    assert invalidated["called"] is True


# ---------------------------------------------------------------------------
# _reliable_terminal_size: bayat COLUMNS/LINES ortam değişkenleri
# ---------------------------------------------------------------------------


def test_reliable_terminal_size_removes_and_restores_env_vars(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    REGRESYON TESTİ (kök neden — bayat terminal boyutu): Rich'in
    `Console.size`'ı, gerçek terminal boyutunu (ioctl) sormadan ÖNCE
    `COLUMNS`/`LINES` ortam değişkenlerini kontrol eder. Bu değişkenler
    bayat/yanlışsa TUI, gerçek terminalden FARKLI bir boyutta render
    edilir (header'ın görünmemesi, içeriğin kayması gibi belirtiler).
    Bu context manager bunları TUI çalışırken geçici olarak kaldırmalı
    ve çıkışta AYNEN geri yüklemelidir.
    """
    monkeypatch.setenv("COLUMNS", "80")
    monkeypatch.setenv("LINES", "24")

    with tui_app._reliable_terminal_size():
        assert "COLUMNS" not in tui_app.os.environ
        assert "LINES" not in tui_app.os.environ

    assert tui_app.os.environ.get("COLUMNS") == "80"
    assert tui_app.os.environ.get("LINES") == "24"


def test_reliable_terminal_size_noop_when_env_vars_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """COLUMNS/LINES zaten ayarlı değilse context manager hiçbir hataya yol açmamalı."""
    monkeypatch.delenv("COLUMNS", raising=False)
    monkeypatch.delenv("LINES", raising=False)

    with tui_app._reliable_terminal_size():
        pass  # exception fırlatmamalı

    assert "COLUMNS" not in tui_app.os.environ
    assert "LINES" not in tui_app.os.environ


def test_reliable_terminal_size_restores_even_on_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """İçeride bir exception oluşsa bile ortam değişkenleri geri yüklenmelidir."""
    monkeypatch.setenv("COLUMNS", "161")

    with pytest.raises(RuntimeError):
        with tui_app._reliable_terminal_size():
            raise RuntimeError("kasıtlı test hatası")

    assert tui_app.os.environ.get("COLUMNS") == "161"


# ---------------------------------------------------------------------------
# _read_key: Ctrl+C (ham modda ISIG kapalı olduğu için manuel ele alınmalı)
# ---------------------------------------------------------------------------


def test_read_key_delegates_to_descriptor_reader(monkeypatch: pytest.MonkeyPatch) -> None:
    """app katmanı terminal parser'ını tekrar etmemeli; portable reader'ı kullanmalı."""
    monkeypatch.setattr(tui_app, "read_key", lambda *args, **kwargs: "QUIT")
    assert tui_app._read_key() == "QUIT"


# ---------------------------------------------------------------------------
# run_tui: tty olmayan ortamda çökmeden dönmeli
# ---------------------------------------------------------------------------


def test_run_tui_without_tty_returns_gracefully(
    config, tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from core.database import Database

    db = Database(tmp_path / "test.db")
    db.init_db()

    # Bu test ortamında (ve genelde CI'de) stdin/stdout gerçek bir tty
    # olmayabilir; run_tui bu durumda exception fırlatmadan, temiz bir
    # mesajla geri dönmelidir.
    monkeypatch.setattr(tui_app.sys.stdin, "isatty", lambda: False)

    tui_app.run_tui(config, db)  # exception fırlatırsa test fail olur

    db.close()


def test_run_tui_always_refreshes_live_on_update(
    config, tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    REGRESYON TESTİ (kök neden #1 — asıl bug): `Live` bu projede
    `auto_refresh=False` ile oluşturuluyor (gereksiz arka plan thread'i
    açmamak için). Bu durumda her `live.update()` çağrısı AÇIKÇA
    `refresh=True` geçirmelidir; aksi halde Rich'in `Live.update()`
    varsayılanı (`refresh=False`) nedeniyle ekran hiçbir zaman gerçekten
    yeniden çizilmez ("neredeyse boş ekran" sorununun doğrudan sebebiydi).

    Gerçek bir terminal/tty gerektirmemek için `Live` ve `_raw_terminal`
    burada sahte (fake) implementasyonlarla değiştirilir; yalnızca
    `run_tui`'nin `Live.update()`'i her zaman `refresh=True` ile çağırdığı
    doğrulanır.
    """
    from core.database import Database

    db = Database(tmp_path / "test.db")
    db.init_db()

    monkeypatch.setattr(tui_app.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(tui_app.sys.stdout, "isatty", lambda: True)
    monkeypatch.setenv("TERM", "xterm-256color")

    # Gerçek termios/tty çağrıları bu test ortamında (tty olmadığı için)
    # başarısız olur; burada yalnızca Live'ın nasıl çağrıldığını test
    # ediyoruz, ham terminal moduna gerçekten girmiyoruz.
    monkeypatch.setattr(tui_app, "_raw_terminal", lambda stream: contextlib.nullcontext())

    update_calls: list[bool] = []

    class FakeLive:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def __enter__(self) -> "FakeLive":
            return self

        def __exit__(self, *args) -> bool:
            return False

        def update(self, renderable, refresh: bool = False) -> None:
            update_calls.append(refresh)

    monkeypatch.setattr(tui_app, "Live", FakeLive)

    # İlk tuş DOWN (bir güncelleme daha tetikler), ikincisi QUIT (döngüyü sonlandırır).
    keys = iter(["DOWN", "QUIT"])
    monkeypatch.setattr(tui_app, "_read_key", lambda: next(keys))

    tui_app.run_tui(config, db)

    db.close()

    assert len(update_calls) >= 2, "En az ilk çizim + bir tuş sonrası güncelleme beklenir"
    assert all(refresh is True for refresh in update_calls), (
        "live.update() HER çağrıda refresh=True geçirmelidir "
        "(auto_refresh=False olduğu için, aksi halde ekran hiç yenilenmez)"
    )


def test_run_tui_redraws_on_real_sigwinch_signal(
    config, tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    REGRESYON TESTİ (kabul kriteri #3 — terminal boyutu değişince uyum):
    `run_tui`, `SIGWINCH` (terminal yeniden boyutlandırma sinyali) için
    gerçek bir `signal.signal()` işleyicisi kurar. Bu test GERÇEK bir
    `os.kill(pid, SIGWINCH)` sinyali gönderir (mock değil) ve bunun
    sonucunda bir sonraki döngü turunda (tuş beklenmeden) ekstra bir
    `live.update()` tetiklendiğini doğrular.
    """
    import os
    import signal

    from core.database import Database

    db = Database(tmp_path / "test.db")
    db.init_db()

    monkeypatch.setattr(tui_app.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(tui_app.sys.stdout, "isatty", lambda: True)
    monkeypatch.setenv("TERM", "xterm-256color")
    monkeypatch.setattr(tui_app, "_raw_terminal", lambda stream: contextlib.nullcontext())

    update_calls: list[bool] = []

    class FakeLive:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def __enter__(self) -> "FakeLive":
            return self

        def __exit__(self, *args) -> bool:
            return False

        def update(self, renderable, refresh: bool = False) -> None:
            update_calls.append(refresh)

    monkeypatch.setattr(tui_app, "Live", FakeLive)

    call_count = {"n": 0}

    def fake_read_key() -> str:
        call_count["n"] += 1
        if call_count["n"] == 1:
            # GERÇEK bir işletim sistemi sinyali gönderiyoruz — mock değil.
            os.kill(os.getpid(), signal.SIGWINCH)
            return ""  # bu turda tuş yok; ama resize bekliyor olmalı
        return "QUIT"

    monkeypatch.setattr(tui_app, "_read_key", fake_read_key)

    tui_app.run_tui(config, db)

    db.close()

    # update_calls: [ilk çizim] + [SIGWINCH sonrası resize redraw] + [QUIT sonrası redraw]
    assert len(update_calls) >= 3, (
        "Gerçek SIGWINCH sinyali sonrası tuş beklenmeden ekstra bir "
        "yeniden çizim tetiklenmedi"
    )
    assert all(refresh is True for refresh in update_calls)


def test_handle_key_sync_uses_last_discovery(config, tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from core.database import Database

    db = Database(tmp_path / "sync.db")
    db.init_db()
    state = AppState(current_screen=Screen.DISCOVERY)
    state.last_scan_hosts = [DiscoveredHost(ip="192.168.1.5", mac="AA:BB:CC:DD:EE:FF")]

    monkeypatch.setattr(tui_app, "sync_known_discovered", lambda db_arg, state_arg: (1, None))
    tui_app._handle_key("SYNC", state, config, db)

    assert state.status_message == "1 kayıtlı cihaz güncellendi."
    db.close()


def test_handle_key_sync_outside_device_screens_does_not_write(
    config, tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from core.database import Database

    db = Database(tmp_path / "sync.db")
    db.init_db()
    state = AppState(current_screen=Screen.CONFIGURATION)

    def fail(*args, **kwargs):
        raise AssertionError("sync should not run on Configuration")

    monkeypatch.setattr(tui_app, "sync_known_discovered", fail)
    tui_app._handle_key("SYNC", state, config, db)

    assert "yalnız Discovery/Devices" in (state.status_message or "")
    db.close()
