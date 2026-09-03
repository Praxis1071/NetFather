"""Capability-aware terminal handling for Linux, macOS and Windows.

POSIX terminals use cbreak mode and descriptor-level ANSI input parsing.
Windows consoles use ``msvcrt`` key events, avoiding ``select``/``termios``
APIs that are not available there.  The rest of the TUI only sees symbolic
keys and normalized rendering capabilities.
"""

from __future__ import annotations

import contextlib
import os
import re
import select
import sys
import time
from dataclasses import dataclass
from enum import Enum
from typing import IO, Iterator, Mapping

from core.platform import PlatformFamily, platform_family


class TerminalMode(str, Enum):
    AUTO = "auto"
    FULLSCREEN = "fullscreen"
    INLINE = "inline"
    PLAIN = "plain"


@dataclass(frozen=True)
class TerminalCapabilities:
    interactive: bool
    term: str
    mode: TerminalMode
    alternate_screen: bool
    cursor_addressing: bool
    reason: str = ""


_DUMB_TERMS = {"", "dumb", "unknown", "cons25"}
_ANSI_TERM_PREFIXES = (
    "ansi",
    "alacritty",
    "foot",
    "gnome",
    "konsole",
    "kitty",
    "linux",
    "putty",
    "rxvt",
    "screen",
    "st",
    "tmux",
    "vt",
    "wezterm",
    "windows",
    "xterm",
)
_TRUTHY = {"1", "true", "yes", "on"}
_CSI_KEY_RE = re.compile(rb"^\x1b\[(?:[0-9;?<>]*)([ABHF])$")
_SS3_KEY_RE = re.compile(rb"^\x1bO([ABHF])$")


def _parse_mode(value: str | TerminalMode | None) -> TerminalMode:
    if isinstance(value, TerminalMode):
        return value
    if value is None:
        return TerminalMode.AUTO
    try:
        return TerminalMode(value.strip().lower())
    except ValueError:
        return TerminalMode.AUTO


def _terminfo_supports_alternate_screen(term: str, fd: int) -> bool | None:
    if not term or term in _DUMB_TERMS:
        return False
    try:
        import curses
    except ImportError:
        return None
    try:
        curses.setupterm(term=term, fd=fd)
        return bool(curses.tigetstr("smcup") and curses.tigetstr("rmcup"))
    except (curses.error, OSError):
        return None


def _supports_cursor_addressing(term: str, family: PlatformFamily) -> bool:
    if family is PlatformFamily.WINDOWS:
        # Rich enables Windows VT support where available and has its own
        # console compatibility path.  Inline mode therefore works even when
        # Windows does not expose a Unix-style TERM variable.
        return True
    lowered = term.lower()
    if lowered in _DUMB_TERMS:
        return False
    return lowered.startswith(_ANSI_TERM_PREFIXES) or "color" in lowered


def detect_terminal_capabilities(
    stdin: IO[str] = sys.stdin,
    stdout: IO[str] = sys.stdout,
    environ: Mapping[str, str] | None = None,
    requested_mode: str | TerminalMode | None = None,
    platform_name: str | None = None,
) -> TerminalCapabilities:
    """Detect a safe TUI rendering strategy for the current host terminal."""
    env = os.environ if environ is None else environ
    family = platform_family(platform_name)
    try:
        interactive = bool(stdin.isatty() and stdout.isatty())
    except (AttributeError, OSError):
        interactive = False

    raw_term = env.get("TERM", "").strip().lower()
    term = raw_term or ("windows-console" if family is PlatformFamily.WINDOWS else "")
    cursor_addressing = _supports_cursor_addressing(term, family)

    env_mode = env.get("NETFATHER_TUI_MODE")
    mode = _parse_mode(
        env_mode
        if requested_mode in (None, TerminalMode.AUTO, "auto") and env_mode
        else requested_mode
    )
    if mode is TerminalMode.AUTO and env.get("NETFATHER_TUI_FULLSCREEN", "").lower() in _TRUTHY:
        mode = TerminalMode.FULLSCREEN

    if not interactive:
        return TerminalCapabilities(False, term, TerminalMode.PLAIN, False, False, "not a TTY")

    if mode is TerminalMode.PLAIN or (term in _DUMB_TERMS and family is not PlatformFamily.WINDOWS):
        return TerminalCapabilities(True, term, TerminalMode.PLAIN, False, False, "limited TERM")

    try:
        fd = stdout.fileno()
    except (AttributeError, OSError):
        fd = 1

    if family is PlatformFamily.WINDOWS:
        alt_screen: bool | None = True
    else:
        alt_screen = _terminfo_supports_alternate_screen(term, fd)
        if alt_screen is None:
            alt_screen = term.startswith(_ANSI_TERM_PREFIXES)

    if mode is TerminalMode.FULLSCREEN:
        if alt_screen and cursor_addressing:
            return TerminalCapabilities(True, term, TerminalMode.FULLSCREEN, True, True)
        if cursor_addressing:
            return TerminalCapabilities(
                True, term, TerminalMode.INLINE, bool(alt_screen), True,
                "fullscreen unsupported; using inline mode",
            )
        return TerminalCapabilities(
            True, term, TerminalMode.PLAIN, bool(alt_screen), False,
            "cursor addressing unavailable; using plain mode",
        )

    if mode is TerminalMode.INLINE:
        if cursor_addressing:
            return TerminalCapabilities(True, term, TerminalMode.INLINE, bool(alt_screen), True)
        return TerminalCapabilities(True, term, TerminalMode.PLAIN, bool(alt_screen), False, "limited TERM")

    # AUTO is compatibility-first.  Do not depend on alternate-screen even if
    # the terminal advertises it; users can opt into fullscreen explicitly.
    if cursor_addressing:
        return TerminalCapabilities(True, term, TerminalMode.INLINE, bool(alt_screen), True)
    return TerminalCapabilities(True, term, TerminalMode.PLAIN, bool(alt_screen), False, "limited TERM")


@contextlib.contextmanager
def terminal_input_mode(
    stream: IO[str],
    platform_name: str | None = None,
) -> Iterator[None]:
    """Enable immediate key delivery on POSIX; Windows needs no mode switch."""
    if platform_family(platform_name) is PlatformFamily.WINDOWS:
        yield
        return

    import termios
    import tty

    fd = stream.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd, termios.TCSANOW)
        yield
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def decode_key_sequence(sequence: bytes) -> str:
    if not sequence:
        return ""
    if sequence in (b"\x03", b"q", b"Q"):
        return "QUIT"
    if sequence in (b"\r", b"\n"):
        return "ENTER"
    if sequence in (b"r", b"R"):
        return "REFRESH"
    if sequence in (b"s", b"S"):
        return "SYNC"
    if sequence in (b"j", b"J"):
        return "DOWN"
    if sequence in (b"k", b"K"):
        return "UP"
    if sequence == b"g":
        return "HOME"
    if sequence == b"G":
        return "END"

    match = _CSI_KEY_RE.fullmatch(sequence)
    if match:
        return {b"A": "UP", b"B": "DOWN", b"H": "HOME", b"F": "END"}[match.group(1)]
    match = _SS3_KEY_RE.fullmatch(sequence)
    if match:
        return {b"A": "UP", b"B": "DOWN", b"H": "HOME", b"F": "END"}[match.group(1)]
    if sequence in (b"\x1b[1~", b"\x1b[7~"):
        return "HOME"
    if sequence in (b"\x1b[4~", b"\x1b[8~"):
        return "END"
    return ""


def decode_windows_key(first: str, second: str | None = None) -> str:
    """Translate ``msvcrt.getwch`` events into NetFather symbolic keys."""
    if first in ("\x00", "\xe0"):
        return {
            "H": "UP",
            "P": "DOWN",
            "G": "HOME",
            "O": "END",
        }.get(second or "", "")
    mapping = {
        "\x03": "QUIT",
        "q": "QUIT",
        "Q": "QUIT",
        "\r": "ENTER",
        "\n": "ENTER",
        "r": "REFRESH",
        "R": "REFRESH",
        "s": "SYNC",
        "S": "SYNC",
        "j": "DOWN",
        "J": "DOWN",
        "k": "UP",
        "K": "UP",
        "g": "HOME",
        "G": "END",
    }
    return mapping.get(first, "")


def _sequence_is_complete(sequence: bytes) -> bool:
    if not sequence:
        return False
    if sequence[0] != 0x1B:
        return True
    if len(sequence) == 1:
        return False
    if sequence.startswith((b"\x1b[", b"\x1bO")):
        return len(sequence) >= 3 and 0x40 <= sequence[-1] <= 0x7E
    return len(sequence) >= 2


def _read_windows_key(timeout: float) -> str:
    try:
        import msvcrt
    except ImportError:
        return ""

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if msvcrt.kbhit():
                first = msvcrt.getwch()
                if first in ("\x00", "\xe0"):
                    second = msvcrt.getwch()
                    return decode_windows_key(first, second)
                return decode_windows_key(first)
        except OSError:
            return ""
        time.sleep(0.01)
    return ""


def _read_posix_key(stream: IO[str], timeout: float, escape_timeout: float) -> str:
    try:
        fd = stream.fileno()
    except (AttributeError, OSError):
        return ""
    try:
        ready, _, _ = select.select([fd], [], [], timeout)
    except (OSError, ValueError):
        return ""
    if not ready:
        return ""
    try:
        first = os.read(fd, 1)
    except OSError:
        return ""
    if not first:
        return ""
    if first != b"\x1b":
        return decode_key_sequence(first)

    sequence = bytearray(first)
    deadline = time.monotonic() + escape_timeout
    while len(sequence) < 32 and not _sequence_is_complete(bytes(sequence)):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        try:
            ready, _, _ = select.select([fd], [], [], remaining)
        except (OSError, ValueError):
            break
        if not ready:
            break
        try:
            chunk = os.read(fd, 1)
        except OSError:
            break
        if not chunk:
            break
        sequence.extend(chunk)
    return decode_key_sequence(bytes(sequence))


def read_key(
    stream: IO[str] = sys.stdin,
    timeout: float = 0.5,
    escape_timeout: float = 0.06,
    platform_name: str | None = None,
) -> str:
    """Read one portable key event from a POSIX terminal or Windows console."""
    if platform_family(platform_name) is PlatformFamily.WINDOWS:
        return _read_windows_key(timeout)
    return _read_posix_key(stream, timeout, escape_timeout)
