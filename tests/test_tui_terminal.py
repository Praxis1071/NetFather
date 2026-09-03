from __future__ import annotations

import io

import pytest

import tui.terminal as terminal
from tui.terminal import TerminalMode, decode_key_sequence, detect_terminal_capabilities


class FakeTTY(io.StringIO):
    def __init__(self, tty: bool = True, fd: int = 1) -> None:
        super().__init__()
        self._tty = tty
        self._fd = fd

    def isatty(self) -> bool:
        return self._tty

    def fileno(self) -> int:
        return self._fd


@pytest.mark.parametrize(
    ("sequence", "expected"),
    [
        (b"\x1b[A", "UP"),
        (b"\x1b[B", "DOWN"),
        (b"\x1bOA", "UP"),
        (b"\x1bOB", "DOWN"),
        (b"\x1b[1;5A", "UP"),
        (b"\x1b[1;2B", "DOWN"),
        (b"\x1b[H", "HOME"),
        (b"\x1bOF", "END"),
        (b"\x1b[1~", "HOME"),
        (b"\x1b[4~", "END"),
        (b"j", "DOWN"),
        (b"k", "UP"),
        (b"q", "QUIT"),
        (b"\x03", "QUIT"),
        (b"\r", "ENTER"),
    ],
)
def test_decode_key_sequences_from_common_terminals(sequence: bytes, expected: str) -> None:
    assert decode_key_sequence(sequence) == expected


@pytest.mark.parametrize(
    "term_name",
    [
        "xterm-256color",
        "screen-256color",
        "tmux-256color",
        "rxvt-unicode-256color",
        "linux",
        "vt100",
        "alacritty",
        "xterm-kitty",
    ],
)
def test_auto_mode_prefers_inline_for_common_terminal_families(term_name: str) -> None:
    caps = detect_terminal_capabilities(
        FakeTTY(), FakeTTY(), {"TERM": term_name}, TerminalMode.AUTO, platform_name="linux"
    )
    assert caps.interactive is True
    assert caps.mode is TerminalMode.INLINE
    assert caps.cursor_addressing is True


def test_dumb_terminal_uses_plain_mode() -> None:
    caps = detect_terminal_capabilities(FakeTTY(), FakeTTY(), {"TERM": "dumb"}, platform_name="linux")
    assert caps.mode is TerminalMode.PLAIN
    assert caps.cursor_addressing is False


def test_non_tty_is_not_interactive() -> None:
    caps = detect_terminal_capabilities(FakeTTY(False), FakeTTY(), {"TERM": "xterm"})
    assert caps.interactive is False
    assert caps.mode is TerminalMode.PLAIN


def test_fullscreen_request_downgrades_when_terminfo_rejects_alt_screen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(terminal, "_terminfo_supports_alternate_screen", lambda term, fd: False)
    caps = detect_terminal_capabilities(
        FakeTTY(), FakeTTY(), {"TERM": "xterm-256color"}, TerminalMode.FULLSCREEN, platform_name="linux"
    )
    assert caps.mode is TerminalMode.INLINE
    assert "fullscreen unsupported" in caps.reason


def test_fullscreen_request_uses_alt_screen_when_supported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(terminal, "_terminfo_supports_alternate_screen", lambda term, fd: True)
    caps = detect_terminal_capabilities(
        FakeTTY(), FakeTTY(), {"TERM": "xterm-256color"}, TerminalMode.FULLSCREEN, platform_name="linux"
    )
    assert caps.mode is TerminalMode.FULLSCREEN
    assert caps.alternate_screen is True


def test_environment_mode_override_is_honored() -> None:
    caps = detect_terminal_capabilities(
        FakeTTY(), FakeTTY(), {"TERM": "xterm-256color", "NETFATHER_TUI_MODE": "plain"}, platform_name="linux"
    )
    assert caps.mode is TerminalMode.PLAIN


def test_windows_console_without_term_uses_inline_mode() -> None:
    caps = detect_terminal_capabilities(
        FakeTTY(), FakeTTY(), {}, TerminalMode.AUTO, platform_name="win32"
    )
    assert caps.interactive is True
    assert caps.term == "windows-console"
    assert caps.mode is TerminalMode.INLINE


def test_windows_extended_key_decoder() -> None:
    assert terminal.decode_windows_key("\xe0", "H") == "UP"
    assert terminal.decode_windows_key("\xe0", "P") == "DOWN"
    assert terminal.decode_windows_key("\xe0", "G") == "HOME"
    assert terminal.decode_windows_key("\xe0", "O") == "END"
    assert terminal.decode_windows_key("q") == "QUIT"


def test_windows_terminal_input_mode_is_noop() -> None:
    with terminal.terminal_input_mode(FakeTTY(), platform_name="win32"):
        pass
