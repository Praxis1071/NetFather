"""Continuous local-network presence reconciliation."""
from __future__ import annotations

import threading
from typing import Callable

from core.database import Database
from core.logger import get_logger
from manager.device_manager import DeviceManager
from network.discovery_service import DiscoveryService
from network.presence import PresenceEvent, PresenceMonitor

log = get_logger("live_presence")


class LivePresenceService:
    """Turn Linux neighbor notifications into debounced discovery refreshes.

    Reconciliation is single-flight: event-driven and safety-timer scans share
    one lock. Shutdown prevents new scans and waits for an in-flight scan to
    finish before the owning application closes the database.
    """

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
        self._reconcile_lock = threading.Lock()
        self._stopped = True
        self._event_timer: threading.Timer | None = None
        self._safety_timer: threading.Timer | None = None

    @property
    def running(self) -> bool:
        return not self._stopped and self.monitor.running

    def start(self) -> None:
        with self._lock:
            if not self._stopped:
                return
            self._stopped = False
        try:
            self.monitor.start()
        except Exception:
            with self._lock:
                self._stopped = True
            raise
        self._schedule_periodic_safety_scan()

    def stop(self) -> None:
        """Stop event sources and wait until no reconciliation can use the DB."""
        with self._lock:
            if self._stopped:
                # Still synchronize with a possible scan started before a
                # previous stop completed.
                timers: tuple[threading.Timer | None, ...] = ()
            else:
                self._stopped = True
                timers = (self._event_timer, self._safety_timer)
                self._event_timer = None
                self._safety_timer = None

        for timer in timers:
            if timer is None:
                continue
            timer.cancel()
            if timer is not threading.current_thread():
                timer.join()

        self.monitor.stop()
        # A timer may already have entered _reconcile when stop() was called.
        # Acquiring this lock makes database.close() safe after stop() returns.
        with self._reconcile_lock:
            pass

    def _on_presence_event(self, event: PresenceEvent) -> None:
        with self._lock:
            if self._stopped:
                return

        # Cache deletion or a failed neighbor probe is a hint to reconcile,
        # not proof that the device has left every observed network path.
        if event.mac and event.kind == "added":
            try:
                self.device_manager.update_presence(
                    event.mac,
                    online=True,
                    ip=event.address,
                )
            except Exception:
                # Preserve the monitor thread even if one persistence update
                # fails; reconciliation can repair state on the next scan.
                log.exception("Unable to persist a neighbor presence event")

        with self._lock:
            if self._stopped:
                return
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
        # Acquire before checking stopped so stop() can prevent a queued scan
        # from starting and can wait for a scan already in progress.
        with self._reconcile_lock:
            with self._lock:
                if self._stopped:
                    return
            try:
                if self.discovery.running:
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
                with self._lock:
                    should_notify = not self._stopped
                if should_notify and self.on_reconciled is not None:
                    try:
                        self.on_reconciled(snapshot)
                    except Exception:
                        log.exception("Live presence reconciliation callback failed")
            except Exception:
                # Timer exceptions must not permanently disable the safety
                # path. Log and let finally schedule the next attempt.
                log.exception("Live presence reconciliation failed")
            finally:
                self._schedule_periodic_safety_scan()

    def _schedule_periodic_safety_scan(self) -> None:
        with self._lock:
            if self._stopped:
                return
            if self._safety_timer is not None and self._safety_timer.is_alive():
                return
            self._safety_timer = threading.Timer(
                float(self.interval_seconds), self._safety_reconcile
            )
            self._safety_timer.daemon = True
            self._safety_timer.start()

    def _safety_reconcile(self) -> None:
        with self._lock:
            self._safety_timer = None
            if self._stopped:
                return
        self._reconcile()
