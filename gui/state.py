"""Shared state exposed to GTK4 pages and background services."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass(slots=True)
class NetworkState:
    """Small, UI-safe snapshot of live network state."""

    interface: str | None = None
    local_ip: str | None = None
    gateway: str | None = None
    online_devices: int = 0
    known_devices: int = 0
    scanning: bool = False
    status_message: str = "Ready"


@dataclass(slots=True)
class ApplicationState:
    """Central application state with lightweight change notifications.

    The state object contains plain Python data only. GTK widgets must not be
    stored here, which keeps the core state independent from the GTK view
    layer and makes it safe to test without starting a graphical session.
    """

    network: NetworkState = field(default_factory=NetworkState)
    _listeners: list[Callable[[], None]] = field(default_factory=list, repr=False)

    def subscribe(self, callback: Callable[[], None]) -> Callable[[], None]:
        """Register a listener and return an unsubscribe callback."""
        self._listeners.append(callback)

        def unsubscribe() -> None:
            try:
                self._listeners.remove(callback)
            except ValueError:
                pass

        return unsubscribe

    def notify_changed(self) -> None:
        """Notify listeners after state has been updated."""
        for callback in tuple(self._listeners):
            callback()
