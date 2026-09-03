"""Terminal capability detection and portable keyboard input for the TUI.

The TUI intentionally keeps terminal-specific behavior in this module.  The
rest of the application only deals with symbolic key names and a small set of
rendering modes.  This makes the UI usable through common Linux terminal
emulators, terminal multiplexers (tmux/screen), SSH sessions, IDE terminals,
and conservative/dumb terminals without hard-coding one escape-sequence
implementation.
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


class TerminalMode(str, Enum):
    """Rendering strategy used by the TUI."""

    AUTO = "auto"
    FULLSCREEN = "fullscreen"
    INLINE = "inline"
    PLAIN = "plain"


@dataclass(frozen=True)
class TerminalCapabilities:
    """Normalized capabilities relevant to NetFather's terminal UI."""

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
    normalized = value.strip().lower()
    try:
        return TerminalMode(normalized)
    except ValueError:
        return TerminalMode.AUTO


def _terminfo_supports_alternate_screen(term: str, fd: int) -> bool | None:
    """Return terminfo's alternate-screen verdict, or None if unavailable."""
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


def _supports_cursor_addressing(term: str) -> bool:
    """Conservative cursor-addressing check suitable for auto mode."""
    lowered = term.lower()
    if lowered in _DUMB_TERMS:
        return False
    return lowered.startswith(_ANSI_TERM_PREFIXES) or "color" in lowered


def detect_terminal_capabilities(
    stdin: IO[str] = sys.stdin,
    stdout: IO[str] = sys.stdout,
    environ: Mapping[str, str] | None = None,
    requested_mode: str | TerminalMode | None = None,
) -> TerminalCapabilities:
    """Detect a safe rendering mode for the current terminal.

    ``auto`` is deliberately compatibility-first: it uses Rich's inline Live
    mode rather than requiring the alternate-screen buffer.  Fullscreen mode
    remains available explicitly (``netfather tui --mode fullscreen`` or
    ``NETFATHER_TUI_MODE=fullscreen``) and is automatically downgraded when
    terminfo says the terminal does not support alternate-screen switching.
    """

    env = os.environ if environ is None else environ
    try:
        interactive = bool(stdin.isatty() and stdout.isatty())
    except (AttributeError, OSError):
        interactive = False

    term = env.get("TERM", "").strip().lower()
    cursor_addressing = _supports_cursor_addressing(term)

    env_mode = env.get("NETFATHER_TUI_MODE")
    mode = _parse_mode(env_mode if requested_mode in (None, TerminalMode.AUTO, "auto") and env_mode else requested_mode)

    # Backwards-friendly single-purpose override for users/scripts.
    if mode is TerminalMode.AUTO and env.get("NETFATHER_TUI_FULLSCREEN", "").lower() in _TRUTHY:
        mode = TerminalMode.FULLSCREEN

    if not interactive:
        return TerminalCapabilities(False, term, TerminalMode.PLAIN, False, False, "not a TTY")

    if mode is TerminalMode.PLAIN or term in _DUMB_TERMS:
        return TerminalCapabilities(True, term, TerminalMode.PLAIN, False, False, "limited TERM")

    try:
        fd = stdout.fileno()
    except (AttributeError, OSError):
        fd = 1

    alt_screen = _terminfo_supports_alternate_screen(term, fd)
    if alt_screen is None:
        # Missing terminfo entries are common for newer emulators on minimal
        # systems.  Known ANSI families are a reasonable fallback only for an
        # explicitly requested fullscreen mode.
        alt_screen = term.startswith(_ANSI_TERM_PREFIXES)

    if mode is TerminalMode.FULLSCREEN:
        if alt_screen and cursor_addressing:
            return TerminalCapabilities(True, term, TerminalMode.FULLSCREEN, True, True)
        if cursor_addressing:
            return TerminalCapabilities(
                True,
                term,
                TerminalMode.INLINE,
                bool(alt_screen),
                True,
                "fullscreen unsupported; using inline mode",
            )
        return TerminalCapabilities(
            True,
            term,
            TerminalMode.PLAIN,
            bool(alt_screen),
            False,
            "cursor addressing unavailable; using plain mode",
        )

    if mode is TerminalMode.INLINE:
        if cursor_addressing:
            return TerminalCapabilities(True, term, TerminalMode.INLINE, bool(alt_screen), True)
        return TerminalCapabilities(True, term, TerminalMode.PLAIN, bool(alt_screen), False, "limited TERM")

    # AUTO: prefer the least surprising portable Live mode.  This avoids
    # terminals/multiplexers that advertise smcup/rmcup but implement the
    # alternate buffer differently or disable it by policy.
    if cursor_addressing:
        return TerminalCapabilities(True, term, TerminalMode.INLINE, bool(alt_screen), True)
    return TerminalCapabilities(True, term, TerminalMode.PLAIN, bool(alt_screen), False, "limited TERM")


@contextlib.contextmanager
def terminal_input_mode(stream: IO[str]) -> Iterator[None]:
    """Put a POSIX terminal into cbreak mode and restore it reliably.

    cbreak is intentionally used instead of raw mode: it provides immediate
    key delivery while preserving signal handling and more of the terminal's
    normal input/output behavior.  This is substantially friendlier to SSH,
    tmux/screen and IDE-integrated terminals.
    """

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
    """Translate a terminal byte sequence into a NetFather symbolic key."""
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

    # CSI arrows: ESC [ A/B and modifier variants such as ESC [ 1 ; 5 A.
    match = _CSI_KEY_RE.fullmatch(sequence)
    if match:
        final = match.group(1)
        return {b"A": "UP", b"B": "DOWN", b"H": "HOME", b"F": "END"}[final]

    # SS3 arrows/home/end used by application cursor mode on some terminals.
    match = _SS3_KEY_RE.fullmatch(sequence)
    if match:
        final = match.group(1)
        return {b"A": "UP", b"B": "DOWN", b"H": "HOME", b"F": "END"}[final]

    # Common Home/End key encodings.
    if sequence in (b"\x1b[1~", b"\x1b[7~"):
        return "HOME"
    if sequence in (b"\x1b[4~", b"\x1b[8~"):
        return "END"

    return ""


def _sequence_is_complete(sequence: bytes) -> bool:
    if not sequence:
        return False
    if sequence[0] != 0x1B:
        return True
    if len(sequence) == 1:
        return False
    if sequence.startswith((b"\x1b[", b"\x1bO")):
        # ANSI control sequences end with a byte in the 0x40..0x7e range.
        return len(sequence) >= 3 and 0x40 <= sequence[-1] <= 0x7E
    return len(sequence) >= 2


def read_key(
    stream: IO[str] = sys.stdin,
    timeout: float = 0.5,
    escape_timeout: float = 0.06,
) -> str:
    """Read one key event without relying on TextIO buffering."""

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
