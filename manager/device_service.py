"""Application-facing device management service for GTK4."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from core.database import Database
from manager.device_manager import DeviceManager
from models.device import Device
from sqlalchemy import select
from models.device_observation import DeviceObservationRecord
from models.network_evidence import AddressEvidence, ServiceEvidence, IdentityAlias
from models.event import Event
from manager.policy_engine import PolicyEngine


@dataclass(frozen=True, slots=True)
class DeviceSnapshot:
    """Immutable view of registered devices for the UI."""

    devices: tuple[Device, ...]
    selected_name: str | None = None
    error: str | None = None


class DeviceService:
    """Keep GTK device workflows on top of the existing DeviceManager."""

    def __init__(self, database: Database) -> None:
        self.manager = DeviceManager(database)
        self._listeners: list[Callable[[DeviceSnapshot], None]] = []
        self._snapshot = DeviceSnapshot(tuple(self.manager.list_devices()))

    @property
    def snapshot(self) -> DeviceSnapshot:
        return self._snapshot

    def subscribe(self, callback: Callable[[DeviceSnapshot], None]) -> Callable[[], None]:
        self._listeners.append(callback)

        def unsubscribe() -> None:
            try:
                self._listeners.remove(callback)
            except ValueError:
                pass

        return unsubscribe

    def refresh(self, selected_name: str | None = None) -> DeviceSnapshot:
        devices = tuple(self.manager.list_devices())
        selected = selected_name if any(d.name == selected_name for d in devices) else None
        self._snapshot = DeviceSnapshot(devices, selected)
        self._emit()
        return self._snapshot

    def update(
        self,
        current_name: str,
        *,
        new_name: str,
        ip: str | None,
        vendor: str | None,
        device_type: str,
    ) -> DeviceSnapshot:
        self.manager.update_device(
            current_name,
            new_name=new_name,
            ip=ip,
            vendor=vendor,
            device_type=device_type,
        )
        return self.refresh(new_name.strip())

    def delete(self, name: str) -> DeviceSnapshot:
        self.manager.delete_device(name)
        return self.refresh()

    def details(self, name: str) -> dict:
        device = self.manager.get_device_by_name(name)
        with self.manager.db.session() as session:
            observations = list(session.scalars(select(DeviceObservationRecord).where(
                DeviceObservationRecord.device_id == device.id).order_by(DeviceObservationRecord.observed_at.desc()).limit(100)))
            addresses = list(session.scalars(select(AddressEvidence).where(AddressEvidence.device_id == device.id)))
            services = list(session.scalars(select(ServiceEvidence).where(ServiceEvidence.device_id == device.id)
                .order_by(ServiceEvidence.observed_at.desc()).limit(20)))
            aliases = list(session.scalars(select(IdentityAlias).where(IdentityAlias.device_id == device.id)))
            events = list(session.scalars(select(Event).where(Event.device_mac.in_([device.mac, *(a.mac for a in aliases)]))
                .order_by(Event.timestamp.desc(), Event.id.desc()).limit(20)))
            for item in (*observations, *addresses, *services, *aliases, *events):
                session.expunge(item)
        from manager.profile_manager import ProfileManager
        from firewall.backends import NftablesBackend
        try:
            blocked = NftablesBackend().read_blocked_ips()
            enforcement = "Unknown / unverified" if blocked is None else ("Blocked" if device.ip in blocked else "Not blocked by NetFather")
        except Exception as exc:
            enforcement = f"Unknown / unverified: {exc}"
        return dict(device=device, observations=observations, addresses=addresses, services=services,
            aliases=aliases, events=events, policy=PolicyEngine(self.manager.db).evaluate_device(name),
            profiles=ProfileManager(self.manager.db).list_profiles(device_name=name), enforcement=enforcement)

    def _emit(self) -> None:
        for callback in tuple(self._listeners):
            callback(self._snapshot)
