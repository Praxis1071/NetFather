"""Continuous local-network presence reconciliation."""
from __future__ import annotations

import threading
from typing import Callable

from core.database import Database
from manager.device_manager import DeviceManager
from network.discovery_service import DiscoveryService
from network.presence import PresenceEvent, PresenceMonitor


class LivePresenceService:
    """Turn Linux neighbor notifications into debounced discovery refreshes."""

    def __init__(
        self,
        database: Database,
        *,
        interval_seconds: int = 15,
        on_reconciled: Callable[[object], None] | None = None,
    ) -> None:
        self.interval_seconds = max(3, interval_seconds)
        self.on_reconciled = on_reconciled
        self.discovery = DiscoveryService(device_manager=DeviceManager(database))
        self.monitor = PresenceMonitor(self._on_presence_event)
        self._lock = threading.Lock()
        self._timer: threading.Timer | None = None
        self._pending = False
        self._stopped = True

    @property
    def running(self) -> bool:
        return not self._stopped and self.monitor.running

    def start(self) -> None:
        if self.running:
            return
        self._stopped = False
        self.monitor.start()

    def stop(self) -> None:
        self._stopped = True
        self.monitor.stop()
        with self._lock:
            timer = self._timer
            self._timer = None
            self._pending = False
        if timer is not None:
            timer.cancel()

    def _on_presence_event(self, _event: PresenceEvent) -> None:
        if self._stopped:
            return
        with self._lock:
            self._pending = True
            if self._timer is not None and self._timer.is_alive():
                return
            self._timer = threading.Timer(0.75, self._reconcile)
            self._timer.daemon = True
            self._timer.start()

    def _reconcile(self) -> None:
        with self._lock:
            self._pending = False
            self._timer = None
        if self._stopped or self.discovery.running:
            return
        snapshot = self.discovery.scan(
            timeout_seconds=3,
            active_timeout_seconds=1,
            mode="hybrid",
            hostname_resolution=False,
            vendor_detection=True,
            os_detection=False,
        )
        if self.on_reconciled is not None:
            self.on_reconciled(snapshot)
        if not self._stopped:
            self._schedule_periodic_safety_scan()

    def _schedule_periodic_safety_scan(self) -> None:
        with self._lock:
            if self._timer is not None and self._timer.is_alive():
                return
            self._timer = threading.Timer(float(self.interval_seconds), self._reconcile)
            self._timer.daemon = True
            self._timer.start()
