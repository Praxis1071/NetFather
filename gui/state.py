"""Shared state exposed to GTK4 pages and background services."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from network.identity import DeviceIdentity


@dataclass(slots=True)
class DiscoveryState:
    """UI-safe discovery state; contains no GTK objects."""

    running: bool = False
    mode: str = "hybrid"
    subnet: str = ""
    hostname_resolution: bool = False
    vendor_detection: bool = True
    os_detection: bool = False
    timeout_seconds: int = 5
    active_timeout_seconds: int | None = None
    scanned: int = 0
    identities: tuple[DeviceIdentity, ...] = field(default_factory=tuple)
    error: str | None = None
    status_message: str = "Ready"


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
    """Central application state with lightweight change notifications."""

    network: NetworkState = field(default_factory=NetworkState)
    discovery: DiscoveryState = field(default_factory=DiscoveryState)
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
