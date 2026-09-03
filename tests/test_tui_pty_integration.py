"""Real PTY regression tests for terminal compatibility."""

from __future__ import annotations

import os
import re
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
    reason="PTY integration tests require Linux/Unix",
)


def _dependencies_available() -> bool:
    try:
        import rich  # noqa: F401
        import typer  # noqa: F401
    except ImportError:
        return False
    return True


def _strip_ansi(data: bytes) -> str:
    text = data.decode("utf-8", errors="replace")
    return re.sub(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))", "", text)


def _spawn_netfather_in_pty(
    cols: int = 120,
    rows: int = 32,
    *,
    term: str = "xterm-256color",
    mode: str | None = None,
    send: bytes | None = None,
    timeout: float = 2.0,
) -> tuple[bytes, int | None]:
    import fcntl
    import pty
    import struct
    import termios as termios_mod

    master_fd, slave_fd = pty.openpty()
    winsize = struct.pack("HHHH", rows, cols, 0, 0)
    fcntl.ioctl(slave_fd, termios_mod.TIOCSWINSZ, winsize)

    env = dict(os.environ)
    env["TERM"] = term
    env["COLUMNS"] = "80"  # intentionally stale
    env["LINES"] = "24"
    if mode is not None:
        env["NETFATHER_TUI_MODE"] = mode
    else:
        env.pop("NETFATHER_TUI_MODE", None)
        env.pop("NETFATHER_TUI_FULLSCREEN", None)

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

    output = bytearray()
    fallback_send_at = time.monotonic() + 1.2 if send else None
    deadline = time.monotonic() + timeout
    sent = False

    try:
        while time.monotonic() < deadline:
            # Wait until the first frame/prompt is visible before injecting
            # input.  Slower TERM profiles must not lose the key before
            # cbreak/plain input setup is complete.
            ready_for_input = b"NETFATHER" in output or b"netfather [" in output
            if (
                send is not None
                and not sent
                and (ready_for_input or time.monotonic() >= fallback_send_at)
            ):
                os.write(master_fd, send)
                sent = True

            ready, _, _ = select.select([master_fd], [], [], 0.05)
            if ready:
                try:
                    chunk = os.read(master_fd, 65536)
                except OSError:
                    break
                if not chunk:
                    break
                output.extend(chunk)

            if proc.poll() is not None:
                break
    finally:
        if proc.poll() is None:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                proc.wait(timeout=1)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except ProcessLookupError:
                    pass
                proc.wait(timeout=1)
        os.close(master_fd)

    return bytes(output), proc.returncode


def test_default_tui_renders_without_requiring_alternate_screen() -> None:
    if not _dependencies_available():
        pytest.skip("rich/typer unavailable")

    output, _ = _spawn_netfather_in_pty(cols=161, rows=37)
    plain = _strip_ansi(output)

    assert output
    assert b"\x1b[?1049h" not in output, "auto mode should not require alternate-screen support"
    assert "NETFATHER" in plain
    assert "OVERVIEW" in plain
    assert "Overview" in plain
    assert "Navigate" in plain


def test_tui_exits_cleanly_on_q_in_inline_mode() -> None:
    if not _dependencies_available():
        pytest.skip("rich/typer unavailable")

    output, exit_code = _spawn_netfather_in_pty(send=b"q", timeout=3.0)
    assert exit_code == 0
    assert b"\x1b[?1049h" not in output
    assert b"\x1b[?25h" in output, "cursor should be restored on exit"


@pytest.mark.parametrize(
    "term_name",
    ["xterm-256color", "screen-256color", "tmux-256color", "linux", "vt100"],
)
def test_tui_first_frame_works_across_common_term_values(term_name: str) -> None:
    if not _dependencies_available():
        pytest.skip("rich/typer unavailable")

    output, exit_code = _spawn_netfather_in_pty(term=term_name, send=b"q", timeout=3.0)
    plain = _strip_ansi(output)
    assert exit_code == 0
    assert "NETFATHER" in plain
    assert "Overview" in plain


def test_explicit_fullscreen_mode_uses_alternate_screen_when_supported() -> None:
    if not _dependencies_available():
        pytest.skip("rich/typer unavailable")

    output, exit_code = _spawn_netfather_in_pty(
        term="xterm-256color", mode="fullscreen", send=b"q", timeout=3.0
    )
    assert exit_code == 0
    assert b"\x1b[?1049h" in output
    assert b"\x1b[?1049l" in output


def test_ss3_arrow_sequence_navigates_in_real_pty() -> None:
    if not _dependencies_available():
        pytest.skip("rich/typer unavailable")

    # SS3 Down (ESC O B), Enter, then q.  Some terminals/application cursor
    # modes use SS3 instead of CSI arrows.
    output, exit_code = _spawn_netfather_in_pty(send=b"\x1bOB\rq", timeout=3.0)
    plain = _strip_ansi(output)
    assert exit_code == 0
    assert "ACTIVE VIEW — Devices" in plain


def test_dumb_term_falls_back_to_plain_mode_and_exits() -> None:
    if not _dependencies_available():
        pytest.skip("rich/typer unavailable")

    output, exit_code = _spawn_netfather_in_pty(term="dumb", send=b"q\n", timeout=3.0)
    plain = _strip_ansi(output)
    assert exit_code == 0
    assert "plain compatibility mode" in plain
    assert "netfather [j/k, enter, r, s, q]>" in plain


def test_tiny_terminal_shows_safe_resize_message_instead_of_broken_layout() -> None:
    if not _dependencies_available():
        pytest.skip("rich/typer unavailable")

    output, exit_code = _spawn_netfather_in_pty(cols=40, rows=10, send=b"q", timeout=3.0)
    plain = _strip_ansi(output)
    assert exit_code == 0
    assert "too small" in plain
    assert "40x10" in plain
