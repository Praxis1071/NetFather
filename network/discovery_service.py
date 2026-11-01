"""Application-facing discovery service."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from threading import RLock
from typing import Callable, TYPE_CHECKING
from concurrent.futures import CancelledError
import json
from sqlalchemy import select

from core.time_utils import utc_now
from network.discovery import DiscoveredHost, observations_from_hosts, scan_network_report
from network.identity import DeviceIdentity, IdentityResolver
from core.logger import get_logger
from core.operations import CancellationToken
from models.device import Device
from models.network_evidence import IdentityAlias, ScanRecord
from models.network_evidence import AddressEvidence

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
    cancelled: bool = False

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
        self._token: CancellationToken | None = None
        self._committing = False
        if device_manager is not None:
            from network.identity import DeviceObservation
            for device in device_manager.list_devices():
                if device.last_seen:
                    identity = self.resolver.observe(DeviceObservation(mac=device.mac, ip=device.ip,
                        hostname=device.hostname, vendor=device.vendor, source="persisted", observed_at=device.last_seen))
                    identity.online = device.online
                    identity.identity_conflict = device.identity_conflict
                    identity.identity_note = device.identity_note
            with device_manager.db.session() as session:
                for path in session.scalars(select(AddressEvidence)):
                    device = session.get(Device, path.device_id)
                    identity = self.resolver.get(device.mac)
                    if identity:
                        identity.ips.add(path.ip)
                        identity.ip_last_seen[path.ip] = path.last_seen
                        if path.interface:
                            identity.interfaces.add(path.interface)

    def cancel(self) -> bool:
        """Cancel before persistence begins; an atomic commit is never interrupted."""
        with self._lock:
            if not self._running or self._committing or self._token is None:
                return False
            self._token.cancel()
            return True

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
        token: CancellationToken | None = None,
        on_progress: Callable[[str], None] | None = None,
        lease_paths: tuple[str, ...] | None = None,
    ) -> DiscoverySnapshot:
        """Run one discovery cycle and reconcile stable identities."""
        with self._lock:
            if self._running:
                raise RuntimeError("Discovery taraması zaten çalışıyor.")
            self._running = True
            self._token = token or CancellationToken()
            self._committing = False
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
                token=self._token,
                on_progress=on_progress,
                lease_paths=lease_paths,
            )
            with self._lock:
                self._token.check()
                self._committing = True
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
                with self.device_manager.db.session() as session:
                    self.resolver.aliases = {
                        alias.mac: session.get(Device, alias.device_id).mac
                        for alias in session.scalars(select(IdentityAlias))
                    }
                    for alias_mac in self.resolver.aliases:
                        self.resolver._identities.pop(alias_mac, None)
            # Do not mutate runtime identity when persistence fails/rolls back.
            identities = self.resolver.reconcile(
                observations,
                mark_missing_offline=report.complete,
                offline_after_seconds=max(1, offline_after_seconds),
            )
            if self.device_manager is not None:
                persistent = {item.mac: item for item in self.device_manager.list_devices()}
                for identity in identities:
                    if identity.mac in persistent:
                        device = persistent[identity.mac]
                        identity.current_ip = device.ip
                        identity.online = device.online
                        identity.identity_conflict = device.identity_conflict
                        identity.identity_note = device.identity_note
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
        except CancelledError:
            snapshot = DiscoverySnapshot(started_at=started, completed_at=utc_now(), scanned=0,
                identities=self.resolver.all(), complete=False, cancelled=True,
                warnings=("Scan cancelled; previous device state was preserved.",))
        except Exception as exc:
            snapshot = DiscoverySnapshot(started_at=started, completed_at=utc_now(), scanned=0, identities=self.resolver.all(), error=str(exc), complete=False)
        finally:
            with self._lock:
                self._snapshot = snapshot
        if self.device_manager is not None:
            try:
                from manager.event_manager import EventManager
                with self.device_manager.db.session() as session:
                    session.add(ScanRecord(started_at=started, completed_at=snapshot.completed_at,
                        mode=mode, complete=snapshot.complete, cancelled=snapshot.cancelled,
                        scanned=snapshot.scanned, warnings=json.dumps(snapshot.warnings)))
                EventManager(self.device_manager.db).record(
                    "discovery_cancelled" if snapshot.cancelled else "discovery_completed",
                    snapshot.error or f"{mode}: {snapshot.scanned} observations; complete={snapshot.complete}")
            except Exception:
                log.exception("Unable to persist discovery cycle history")
        with self._lock:
            self._running = False
            self._token = None
            self._committing = False
            listeners = tuple(self._listeners)
        for callback in listeners:
            try:
                callback(snapshot)
            except Exception:
                # Listener failures must not turn a completed scan into a
                # failed task or prevent other subscribers receiving results.
                log.exception("Discovery snapshot listener failed")
        return snapshot
