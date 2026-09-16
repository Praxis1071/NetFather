"""Live Linux neighbor-presence monitoring for NetFather."""
from __future__ import annotations

import subprocess
import threading
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True, slots=True)
class PresenceEvent:
    """A kernel neighbor-table event observed through ``ip monitor neigh``."""

    raw: str
    kind: str
    address: str | None = None
    mac: str | None = None


def parse_neighbor_event(line: str) -> PresenceEvent | None:
    """Parse the useful parts of an iproute2 neighbor-monitor line."""
    text = line.strip()
    if not text:
        return None
    lower = text.lower()
    kind = "changed"
    if lower.startswith("deleted") or " nud failed" in lower:
        kind = "removed"
    elif lower.startswith("added") or lower.startswith("new"):
        kind = "added"
    tokens = text.replace("/", " ").split()
    address = next((token for token in tokens if _looks_like_ip(token)), None)
    mac = None
    for index, token in enumerate(tokens[:-1]):
        if token.lower() in {"lladdr", "lladdress"} and _looks_like_mac(tokens[index + 1]):
            mac = tokens[index + 1].lower()
            break
    return PresenceEvent(raw=text, kind=kind, address=address, mac=mac)


def _looks_like_ip(value: str) -> bool:
    parts = value.split(".")
    if len(parts) != 4:
        return False
    try:
        return all(0 <= int(part) <= 255 for part in parts)
    except ValueError:
        return False


def _looks_like_mac(value: str) -> bool:
    parts = value.split(":")
    return len(parts) == 6 and all(len(part) == 2 and all(c in "0123456789abcdefABCDEF" for c in part) for part in parts)


class PresenceMonitor:
    """Watch Linux neighbor-table notifications without requiring root."""

    def __init__(self, callback: Callable[[PresenceEvent], None]) -> None:
        self.callback = callback
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._process: subprocess.Popen[str] | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> bool:
        if self.running:
            return True
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="netfather-presence", daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stop.set()
        process = self._process
        if process is not None:
            try:
                process.terminate()
            except OSError:
                pass
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=1.5)
        self._thread = None
        self._process = None

    def _run(self) -> None:
        try:
            self._process = subprocess.Popen(
                ["ip", "monitor", "neigh"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1,
            )
        except (OSError, ValueError):
            return
        process = self._process
        if process.stdout is None:
            return
        try:
            for line in process.stdout:
                if self._stop.is_set():
                    break
                event = parse_neighbor_event(line)
                if event is not None:
                    self.callback(event)
        finally:
            try:
                process.stdout.close()
            except OSError:
                pass
            try:
                process.terminate()
            except OSError:
                pass
            self._process = None
