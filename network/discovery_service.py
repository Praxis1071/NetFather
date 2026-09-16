"""Application-facing discovery service.

This module keeps network discovery independent from GTK widgets. A scan runs
synchronously in the caller's worker thread, then the service reconciles the
observations into stable identities and exposes a compact snapshot to the UI.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from threading import Lock
from typing import Callable

from core.time_utils import utc_now
from network.discovery import DiscoveredHost, observations_from_hosts, scan_network
from network.identity import DeviceIdentity, IdentityResolver


@dataclass(frozen=True, slots=True)
class DiscoverySnapshot:
    """Immutable result of the latest discovery cycle."""

    started_at: datetime
    completed_at: datetime
    scanned: int
    hosts: tuple[DiscoveredHost, ...] = field(default_factory=tuple)
    identities: tuple[DeviceIdentity, ...] = field(default_factory=tuple)
    error: str | None = None


class DiscoveryService:
    """Coordinate discovery, identity reconciliation and state notifications."""

    def __init__(self, resolver: IdentityResolver | None = None) -> None:
        self.resolver = resolver or IdentityResolver()
        self._lock = Lock()
        self._running = False
        self._snapshot: DiscoverySnapshot | None = None
        self._listeners: list[Callable[[DiscoverySnapshot], None]] = []

    @property
    def running(self) -> bool:
        with self._lock:
            return self._running

    @property
    def snapshot(self) -> DiscoverySnapshot | None:
        with self._lock:
            return self._snapshot

    def subscribe(self, callback: Callable[[DiscoverySnapshot], None]) -> Callable[[], None]:
        self._listeners.append(callback)

        def unsubscribe() -> None:
            try:
                self._listeners.remove(callback)
            except ValueError:
                pass

        return unsubscribe

    def scan(
        self,
        *,
        timeout_seconds: int = 5,
        mode: str = "hybrid",
        subnet: str | None = None,
        hostname_resolution: bool = False,
        vendor_detection: bool = True,
        os_detection: bool = False,
        active_timeout_seconds: int | None = None,
    ) -> DiscoverySnapshot:
        """Run one discovery cycle and reconcile stable identities."""
        with self._lock:
            if self._running:
                raise RuntimeError("Discovery taraması zaten çalışıyor.")
            self._running = True
        started = utc_now()
        snapshot: DiscoverySnapshot
        try:
            hosts = scan_network(
                timeout_seconds,
                mode=mode,
                subnet=subnet,
                hostname_resolution=hostname_resolution,
                vendor_detection=vendor_detection,
                os_detection=os_detection,
                active_timeout_seconds=active_timeout_seconds,
            )
            observations = observations_from_hosts(hosts)
            identities = self.resolver.reconcile(observations)
            snapshot = DiscoverySnapshot(
                started_at=started,
                completed_at=utc_now(),
                scanned=len(hosts),
                hosts=tuple(hosts),
                identities=tuple(identities),
            )
        except Exception as exc:
            snapshot = DiscoverySnapshot(
                started_at=started,
                completed_at=utc_now(),
                scanned=0,
                identities=self.resolver.all(),
                error=str(exc),
            )
        finally:
            with self._lock:
                self._running = False
                self._snapshot = snapshot
        for callback in tuple(self._listeners):
            callback(snapshot)
        return snapshot
