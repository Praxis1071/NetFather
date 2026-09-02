"""
Gerçek bir pseudo-terminal (PTY) üzerinden NetFather TUI'sinin ilk render
çıktısını uçtan uca doğrulayan entegrasyon testi.

Bu test gerçek bir alt süreç başlatıp gerçeğe en yakın koşullarda
(gerçek bir pty, gerçek TIOCSWINSZ ile bildirilen terminal boyutu) TUI'yi
çalıştırır. Amaç, "Layout matematiği doğru mu?" (bkz.
test_tui_layout_geometry.py, mock/headless) sorusunu "Rich Live bunu
GERÇEK bir terminale doğru mu yazıyor?" sorusundan ayırmaktır.

Özellikle şu kök-neden düzeltmesini doğrular: pty'ye GERÇEKTEN 161x37
bildirilirken ortam değişkenlerine bilinçli olarak YANLIŞ/bayat bir
COLUMNS=80/LINES=24 konur; TUI'nin ortam değişkenlerini değil gerçek
pty boyutunu kullandığı doğrulanır.

Bu test yalnızca Linux'ta ve `rich`/`typer` kuruluyken çalışabilir; aksi
halde SKIP edilir (gerçek problem gizlenmez — yalnızca bu testin
önkoşulları bu ortamda karşılanmamıştır).
"""

from __future__ import annotations

import os
import signal
import select
import subprocess
import sys
import time
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent

pytestmark = pytest.mark.skipif(
    not sys.platform.startswith("linux"),
    reason="PTY tabanlı gerçek terminal testi yalnızca Linux/Unix'te çalışır",
)


def _dependencies_available() -> bool:
    try:
        import rich  # noqa: F401
        import typer  # noqa: F401
    except ImportError:
        return False
    return True


def _spawn_netfather_in_pty(cols: int, rows: int, timeout: float = 3.0) -> bytes:
    """
    NetFather'ı gerçek bir PTY içinde, verilen terminal boyutuyla başlatır,
    kısa bir süre çalıştırıp güvenli şekilde sonlandırır ve o süre
    boyunca üretilen ham (ANSI escape kodları dahil) çıktıyı döndürür.
    """
    import fcntl
    import pty
    import struct
    import termios as termios_mod

    master_fd, slave_fd = pty.openpty()

    # Gerçek terminal boyutunu pty'ye bildir (kernel seviyesinde TIOCSWINSZ).
    winsize = struct.pack("HHHH", rows, cols, 0, 0)
    fcntl.ioctl(slave_fd, termios_mod.TIOCSWINSZ, winsize)

    env = dict(os.environ)
    env["TERM"] = "xterm-256color"
    # Kasıtlı olarak YANLIŞ/bayat bir COLUMNS/LINES koyuyoruz: gerçek pty
    # boyutu (161x37 gibi) ile ÇELİŞEN bu değerler, kök-neden
    # düzeltmesinin (bunların yok sayılıp gerçek pty boyutunun
    # kullanılması) fiilen işe yaradığını kanıtlamak için var.
    env["COLUMNS"] = "80"
    env["LINES"] = "24"

    proc = subprocess.Popen(
        [sys.executable, "netfather.py"],
        cwd=str(PROJECT_ROOT),
        stdin=slave_fd,
        stdout=slave_fd,
        stderr=slave_fd,
        env=env,
        start_new_session=True,
    )
    os.close(slave_fd)

    output = b""
    deadline = time.time() + timeout
    try:
        while time.time() < deadline:
            ready, _, _ = select.select([master_fd], [], [], 0.1)
            if not ready:
                continue
            try:
                chunk = os.read(master_fd, 65536)
            except OSError:
                break
            if not chunk:
                break
            output += chunk
    finally:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except ProcessLookupError:
                pass
        os.close(master_fd)

    return output


def test_tui_first_frame_renders_in_real_pty_ignoring_stale_env_vars() -> None:
    """
    REGRESYON TESTİ (kök neden — bayat COLUMNS/LINES ortam değişkenleri):
    pty'ye gerçekten 161x37 bildirilirken ortama kasıtlı olarak yanlış
    COLUMNS=80/LINES=24 konur. Düzeltme sonrası TUI, gerçek pty boyutunu
    kullanmalı ve ilk çerçevede beklenen header/nav/footer metinleri
    üretmelidir.
    """
    if not _dependencies_available():
        pytest.skip("rich/typer kurulu değil; gerçek TUI alt süreci başlatılamaz")

    output = _spawn_netfather_in_pty(cols=161, rows=37)

    assert output, "Alt süreçten hiç çıktı alınamadı"

    # screen=True doğru çalışıyorsa alternate screen dizisi gönderilmiş olmalı.
    assert b"\x1b[?1049h" in output, (
        "Alternate screen (ESC[?1049h) dizisi bulunamadı — Live(screen=True) "
        "beklendiği gibi çalışmıyor olabilir"
    )

    # İlk çerçevede beklenen sabit metinler (header/overview/nav/footer).
    assert b"NETFATHER" in output, "Header metni ('NETFATHER') çıktıda bulunamadı"
    assert b"OVERVIEW" in output, "Overview şeridi başlığı çıktıda bulunamadı"
    assert b"Overview" in output, "Navigation'daki 'Overview' öğesi çıktıda bulunamadı"
    assert b"Navigate" in output, "Footer ipucu metni ('Navigate') çıktıda bulunamadı"


def test_tui_exits_cleanly_on_q_key() -> None:
    """
    Gerçek bir pty üzerinden 'q' tuşu gönderildiğinde TUI'nin düzgün
    şekilde sonlandığını (alternate screen'den çıkış dizisini
    gönderdiğini) doğrular.
    """
    if not _dependencies_available():
        pytest.skip("rich/typer kurulu değil; gerçek TUI alt süreci başlatılamaz")

    import fcntl
    import pty
    import struct
    import termios as termios_mod

    master_fd, slave_fd = pty.openpty()
    winsize = struct.pack("HHHH", 37, 161, 0, 0)
    fcntl.ioctl(slave_fd, termios_mod.TIOCSWINSZ, winsize)

    env = dict(os.environ)
    env["TERM"] = "xterm-256color"

    proc = subprocess.Popen(
        [sys.executable, "netfather.py"],
        cwd=str(PROJECT_ROOT),
        stdin=slave_fd,
        stdout=slave_fd,
        stderr=slave_fd,
        env=env,
        start_new_session=True,
    )
    os.close(slave_fd)

    output = b""
    try:
        # İlk çerçevenin çizilmesi için kısa bir bekleme.
        time.sleep(1.0)
        os.write(master_fd, b"q")

        deadline = time.time() + 3.0
        while time.time() < deadline:
            ready, _, _ = select.select([master_fd], [], [], 0.1)
            if not ready:
                if proc.poll() is not None:
                    break
                continue
            try:
                chunk = os.read(master_fd, 65536)
            except OSError:
                break
            if not chunk:
                break
            output += chunk

        exit_code = proc.wait(timeout=3)
    finally:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except ProcessLookupError:
            pass
        os.close(master_fd)

    assert exit_code == 0, f"'q' sonrası süreç temiz çıkmadı (exit code={exit_code})"
    # Alternate screen'den çıkış dizisi (ESC[?1049l) gönderilmiş olmalı.
    assert b"\x1b[?1049l" in output, "Alternate screen'den çıkış dizisi bulunamadı"
