"""Background, cancellable discovery orchestration for the TUI.

The discovery implementation remains in :mod:`network.discovery`; this module
owns lifecycle, progress state, cancellation, and registry reconciliation.
The stdlib worker keeps Scapy/subprocess/network work off the TUI thread.
"""

from __future__ import annotations

import datetime as dt
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, replace
from enum import Enum

from core.config import Config
from core.database import get_database
from core.logger import get_logger
from manager.device_manager import DeviceManager
from network.discovery import DiscoveredHost, scan_network

log = get_logger("tui.scan")


class ScanStatus(str, Enum):
    IDLE = "IDLE"
    SCANNING = "SCANNING"
    CANCELLING = "CANCELLING"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class ScanOptions:
    mode: str
    subnet: str | None
    timeout_seconds: int
    active_timeout_seconds: int | None
    hostname_resolution: bool
    vendor_detection: bool
    os_detection: bool

    @classmethod
    def from_config(cls, config: Config) -> "ScanOptions":
        return cls(
            mode=config.discovery.mode,
            subnet=config.discovery.subnet or None,
            timeout_seconds=config.network.scan_timeout_seconds,
            active_timeout_seconds=config.discovery.active_timeout_seconds,
            hostname_resolution=config.discovery.hostname_resolution,
            vendor_detection=config.discovery.vendor_detection,
            os_detection=config.discovery.os_detection,
        )


@dataclass(frozen=True)
class ScanSnapshot:
    status: ScanStatus = ScanStatus.IDLE
    progress: int = 0
    current_operation: str = "Ready"
    started_at: dt.datetime | None = None
    finished_at: dt.datetime | None = None
    found_count: int = 0
    new_count: int = 0
    updated_count: int = 0
    offline_count: int = 0
    error: str | None = None
    options: ScanOptions | None = None

    @property
    def running(self) -> bool:
        return self.status in {ScanStatus.SCANNING, ScanStatus.CANCELLING}

    @property
    def duration_seconds(self) -> float | None:
        if self.started_at is None:
            return None
        end = self.finished_at or dt.datetime.now()
        return max(0.0, (end - self.started_at).total_seconds())


class ScanController:
    """Single-flight, background, cancellable discovery controller."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="netfather-scan")
        self._future: Future[None] | None = None
        self._cancel_event = threading.Event()
        self._snapshot = ScanSnapshot()
        self._hosts: list[DiscoveredHost] = []
        self._config: Config | None = None

    def snapshot(self) -> ScanSnapshot:
        with self._lock:
            return self._snapshot

    def hosts(self) -> list[DiscoveredHost]:
        with self._lock:
            return list(self._hosts)

    def start(self, config: Config) -> bool:
        with self._lock:
            if self._snapshot.running:
                return False
            self._config = config
            self._hosts = []
            self._cancel_event.clear()
            options = ScanOptions.from_config(config)
            self._snapshot = ScanSnapshot(
                status=ScanStatus.SCANNING,
                progress=5,
                current_operation=self._operation_label(options, "initializing"),
                started_at=dt.datetime.now(),
                options=options,
            )
            self._future = self._executor.submit(self._run, options)
            return True

    def cancel(self) -> bool:
        with self._lock:
            if not self._snapshot.running:
                return False
            self._cancel_event.set()
            self._snapshot = replace(
                self._snapshot,
                status=ScanStatus.CANCELLING,
                current_operation="Stopping scan safely...",
            )
            return True

    def shutdown(self) -> None:
        self._cancel_event.set()
        self._executor.shutdown(wait=False, cancel_futures=True)

    @staticmethod
    def _operation_label(options: ScanOptions, phase: str) -> str:
        mode = options.mode.strip().lower()
        return f"{mode.title()} discovery: {phase}"

    def _publish(self, **changes: object) -> None:
        with self._lock:
            self._snapshot = replace(self._snapshot, **changes)

    def _reconcile(self, hosts: list[DiscoveredHost], config: Config) -> tuple[int, int, int]:
        db = get_database(config.database_path)
        manager = DeviceManager(db)
        return manager.reconcile_discovery(
            hosts,
            auto_register=config.discovery.auto_register,
            offline_after_seconds=config.discovery.offline_after_seconds,
        )

    def _run(self, options: ScanOptions) -> None:
        try:
            if self._cancel_event.is_set():
                self._finish_cancelled()
                return

            config = self._config
            if config is None:
                raise RuntimeError("Scan configuration kayboldu.")

            self._publish(progress=15, current_operation=self._operation_label(options, "discovering hosts"))
            hosts = scan_network(
                timeout_seconds=options.timeout_seconds,
                mode=options.mode,
                subnet=options.subnet,
                hostname_resolution=options.hostname_resolution,
                vendor_detection=options.vendor_detection,
                os_detection=options.os_detection,
                active_timeout_seconds=options.active_timeout_seconds,
            )

            if self._cancel_event.is_set():
                self._finish_cancelled()
                return

            with self._lock:
                self._hosts = list(hosts)
            self._publish(progress=80, current_operation="Correlating discovered devices", found_count=len(hosts))

            new_count, updated_count, offline_count = self._reconcile(hosts, config)
            if self._cancel_event.is_set():
                self._finish_cancelled()
                return

            self._publish(
                status=ScanStatus.COMPLETED,
                progress=100,
                current_operation="Scan complete",
                finished_at=dt.datetime.now(),
                found_count=len(hosts),
                new_count=new_count,
                updated_count=updated_count,
                offline_count=offline_count,
                error=None,
            )
        except Exception as exc:  # noqa: BLE001 - worker must never crash the TUI
            log.exception("Background discovery failed: %s", exc)
            self._publish(
                status=ScanStatus.FAILED,
                progress=100,
                current_operation="Scan failed",
                finished_at=dt.datetime.now(),
                error="Tarama sırasında beklenmeyen bir hata oluştu. Ayrıntılar log dosyasına kaydedildi.",
            )
        finally:
            with self._lock:
                self._future = None

    def _finish_cancelled(self) -> None:
        self._publish(
            status=ScanStatus.CANCELLED,
            progress=0,
            current_operation="Scan cancelled",
            finished_at=dt.datetime.now(),
            error=None,
        )
        with self._lock:
            self._future = None


_controller = ScanController()


def get_scan_controller() -> ScanController:
    return _controller
