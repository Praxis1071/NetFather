"""Application-facing discovery service."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from threading import RLock
from typing import Callable, TYPE_CHECKING

from core.time_utils import utc_now
from network.discovery import DiscoveredHost, observations_from_hosts, scan_network
from network.identity import DeviceIdentity, IdentityResolver

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
            hosts = scan_network(
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
            observations = observations_from_hosts(hosts)
            identities = self.resolver.reconcile(observations)
            new_devices = updated_devices = offline_devices = 0
            if self.device_manager is not None:
                new_devices, updated_devices, offline_devices = self.device_manager.reconcile_discovery(
                    hosts,
                    auto_register=auto_register,
                    offline_after_seconds=offline_after_seconds,
                )
            snapshot = DiscoverySnapshot(started_at=started, completed_at=utc_now(), scanned=len(hosts), hosts=tuple(hosts), identities=tuple(identities), new_devices=new_devices, updated_devices=updated_devices, offline_devices=offline_devices)
        except Exception as exc:
            snapshot = DiscoverySnapshot(started_at=started, completed_at=utc_now(), scanned=0, identities=self.resolver.all(), error=str(exc))
        finally:
            with self._lock:
                self._running = False
                self._snapshot = snapshot
        with self._lock:
            listeners = tuple(self._listeners)
        for callback in listeners:
            callback(snapshot)
        return snapshot
