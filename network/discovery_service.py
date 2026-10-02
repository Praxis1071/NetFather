"""Application-facing discovery service."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from threading import RLock
from typing import Callable, TYPE_CHECKING

from core.time_utils import utc_now
from network.discovery import DiscoveredHost, observations_from_hosts, scan_network_report
from network.identity import DeviceIdentity, IdentityResolver
from core.logger import get_logger

log = get_logger("network.discovery_service")

if TYPE_CHECKING:
    from manager.device_manager import DeviceManager


@dataclass(frozen=True, slots=True)
class DiscoverySnapshot:
    """Immutable result of the latest discovery cycle."""
    started_at: datetime
    completed_at: datetime
    scanned: int
    hosts: tuple[DiscoveredHost, ...] = field(default_factory=tuple)
    identities: tuple[DeviceIdentity, ...] = field(default_factory=tuple)
    new_devices: int = 0
    updated_devices: int = 0
    offline_devices: int = 0
    error: str | None = None
    warnings: tuple[str, ...] = ()
    complete: bool = True

    @property
    def deep_hosts(self) -> tuple[DiscoveredHost, ...]:
        return tuple(host for host in self.hosts if host.scan_method == "nmap")


class DiscoveryService:
    """Coordinate discovery, identity resolution and device persistence."""
    def __init__(self, resolver: IdentityResolver | None = None, device_manager: DeviceManager | None = None) -> None:
        self.resolver = resolver or IdentityResolver()
        self.device_manager = device_manager
        self._lock = RLock()
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
        with self._lock:
            self._listeners.append(callback)

        def unsubscribe() -> None:
            with self._lock:
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
        auto_register: bool = True,
        offline_after_seconds: int = 45,
        active_timeout_seconds: int | None = None,
        deep_udp: bool = True,
        deep_versions: bool = True,
        deep_os: bool = True,
        deep_top_ports: int = 100,
        deep_elevate: bool = False,
    ) -> DiscoverySnapshot:
        """Run one discovery cycle and reconcile stable identities."""
        with self._lock:
            if self._running:
                raise RuntimeError("Discovery taraması zaten çalışıyor.")
            self._running = True
        started = utc_now()
        snapshot: DiscoverySnapshot
        try:
            report = scan_network_report(
                timeout_seconds,
                mode=mode,
                subnet=subnet,
                hostname_resolution=hostname_resolution,
                vendor_detection=vendor_detection,
                os_detection=os_detection,
                active_timeout_seconds=active_timeout_seconds,
                deep_udp=deep_udp,
                deep_versions=deep_versions,
                deep_os=deep_os,
                deep_top_ports=deep_top_ports,
                deep_elevate=deep_elevate,
            )
            hosts = list(report.hosts)
            observations = observations_from_hosts(hosts)
            new_devices = updated_devices = offline_devices = 0
            if self.device_manager is not None:
                new_devices, updated_devices, offline_devices = self.device_manager.reconcile_discovery(
                    hosts,
                    auto_register=auto_register,
                    offline_after_seconds=offline_after_seconds,
                    mark_missing_offline=report.complete,
                )
            # Do not mutate runtime identity when persistence fails/rolls back.
            identities = self.resolver.reconcile(
                observations,
                mark_missing_offline=report.complete,
                offline_after_seconds=max(1, offline_after_seconds),
            )
            snapshot = DiscoverySnapshot(
                started_at=started,
                completed_at=utc_now(),
                scanned=len(hosts),
                hosts=tuple(hosts),
                identities=tuple(identities),
                new_devices=new_devices,
                updated_devices=updated_devices,
                offline_devices=offline_devices,
                warnings=report.warnings,
                complete=report.complete,
            )
        except Exception as exc:
            snapshot = DiscoverySnapshot(started_at=started, completed_at=utc_now(), scanned=0, identities=self.resolver.all(), error=str(exc), complete=False)
        finally:
            with self._lock:
                self._running = False
                self._snapshot = snapshot
        with self._lock:
            listeners = tuple(self._listeners)
        for callback in listeners:
            try:
                callback(snapshot)
            except Exception:
                # Listener failures must not turn a completed scan into a
                # failed task or prevent other subscribers receiving results.
                log.exception("Discovery snapshot listener failed")
        return snapshot
