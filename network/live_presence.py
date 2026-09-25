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
        auto_register: bool = True,
        offline_after_seconds: int = 45,
        on_reconciled: Callable[[object], None] | None = None,
    ) -> None:
        self.interval_seconds = max(3, interval_seconds)
        self.auto_register = auto_register
        self.offline_after_seconds = max(1, offline_after_seconds)
        self.on_reconciled = on_reconciled
        self.device_manager = DeviceManager(database)
        self.discovery = DiscoveryService(device_manager=self.device_manager)
        self.monitor = PresenceMonitor(self._on_presence_event)
        self._lock = threading.Lock()
        self._event_timer: threading.Timer | None = None
        self._safety_timer: threading.Timer | None = None
        self._stopped = True

    @property
    def running(self) -> bool:
        return not self._stopped and self.monitor.running

    def start(self) -> None:
        if self.running:
            return
        self._stopped = False
        self.monitor.start()
        self._schedule_periodic_safety_scan()

    def stop(self) -> None:
        self._stopped = True
        self.monitor.stop()
        with self._lock:
            event_timer = self._event_timer
            safety_timer = self._safety_timer
            self._event_timer = None
            self._safety_timer = None
        if event_timer is not None:
            event_timer.cancel()
        if safety_timer is not None:
            safety_timer.cancel()

    def _on_presence_event(self, event: PresenceEvent) -> None:
        if self._stopped:
            return
        if event.mac and event.kind in {"added", "removed"}:
            self.device_manager.update_presence(
                event.mac,
                online=event.kind == "added",
                ip=event.address,
            )
        with self._lock:
            if self._event_timer is not None and self._event_timer.is_alive():
                return
            self._event_timer = threading.Timer(0.75, self._event_reconcile)
            self._event_timer.daemon = True
            self._event_timer.start()

    def _event_reconcile(self) -> None:
        with self._lock:
            self._event_timer = None
        self._reconcile()

    def _reconcile(self) -> None:
        if self._stopped:
            return
        if self.discovery.running:
            self._schedule_periodic_safety_scan()
            return
        snapshot = self.discovery.scan(
            timeout_seconds=3,
            active_timeout_seconds=1,
            mode="hybrid",
            hostname_resolution=False,
            vendor_detection=True,
            os_detection=False,
            auto_register=self.auto_register,
            offline_after_seconds=self.offline_after_seconds,
        )
        if self.on_reconciled is not None:
            self.on_reconciled(snapshot)
        self._schedule_periodic_safety_scan()

    def _schedule_periodic_safety_scan(self) -> None:
        if self._stopped:
            return
        with self._lock:
            if self._safety_timer is not None and self._safety_timer.is_alive():
                return
            self._safety_timer = threading.Timer(float(self.interval_seconds), self._safety_reconcile)
            self._safety_timer.daemon = True
            self._safety_timer.start()

    def _safety_reconcile(self) -> None:
        with self._lock:
            self._safety_timer = None
        self._reconcile()
