"""Explicit, audited identity review. Never infer physical sameness from a name."""
from __future__ import annotations

from dataclasses import dataclass
from sqlalchemy import select, update

from core.database import Database
from core.exceptions import ValidationError
from manager.device_manager import DeviceManager
from models.device import Device
from models.device_observation import DeviceObservationRecord
from models.event import Event
from models.network_evidence import AddressEvidence, IdentityAlias, ServiceEvidence
from models.profile import Profile
from models.rule import Rule
from network.identity import normalize_mac


def randomized_mac(mac: str) -> bool:
    """Locally administered is a possibility of randomization, not proof of it."""
    return bool(int(normalize_mac(mac).split(":")[0], 16) & 2)


@dataclass(frozen=True)
class IdentityCandidate:
    retained_id: int
    candidate_id: int
    reason: str
    confidence: float = 0.5


class IdentityManager:
    def __init__(self, db: Database) -> None:
        self.db = db

    def candidates(self) -> tuple[IdentityCandidate, ...]:
        devices = DeviceManager(self.db).list_devices()
        result = []
        for old in devices:
            for new in devices:
                if old.id == new.id or not randomized_mac(new.mac) or not old.hostname:
                    continue
                if (old.hostname, old.vendor) != (new.hostname, new.vendor) or not old.vendor:
                    continue
                if old.last_seen and old.last_seen < new.created_at and not old.online:
                    result.append(IdentityCandidate(old.id, new.id,
                        "Same hostname/vendor after a locally administered MAC change; manual verification required."))
        return tuple(result)

    def merge(self, retained_id: int, candidate_id: int, *, expected_macs: tuple[str, str],
              reason: str, confirmed: bool = False) -> None:
        if not confirmed or retained_id == candidate_id or not reason.strip():
            raise ValidationError("Explicit confirmation, distinct devices and a review reason are required.")
        with self.db.session() as session:
            retained, candidate = session.get(Device, retained_id), session.get(Device, candidate_id)
            if not retained or not candidate or (retained.mac, candidate.mac) != tuple(map(normalize_mac, expected_macs)):
                raise ValidationError("Identity changed during review; reload devices.")
            if retained.online and candidate.online:
                raise ValidationError("Both identities are online; merge refused.")
            if retained.identity_conflict or candidate.identity_conflict:
                raise ValidationError("Resolve address conflicts before merging identities.")
            if session.scalar(select(Profile.id).where(Profile.device_id == candidate.id)) or session.scalar(
                select(Rule.id).where(Rule.device_id == candidate.id)
            ):
                raise ValidationError("Unassign candidate policies before merging; policies are never copied silently.")
            for model in (DeviceObservationRecord, ServiceEvidence, IdentityAlias):
                session.execute(update(model).where(model.device_id == candidate.id).values(device_id=retained.id))
            # De-duplicate path keys before moving their complete evidence.
            for path in session.scalars(select(AddressEvidence).where(AddressEvidence.device_id == candidate.id)):
                existing = session.scalar(select(AddressEvidence).where(
                    AddressEvidence.device_id == retained.id, AddressEvidence.ip == path.ip,
                    AddressEvidence.interface == path.interface))
                if existing:
                    existing.first_seen = min(existing.first_seen, path.first_seen)
                    existing.last_seen = max(existing.last_seen, path.last_seen)
                    session.delete(path)
                else:
                    path.device_id = retained.id
            session.add(IdentityAlias(mac=candidate.mac, device_id=retained.id, reason=reason.strip()[:512]))
            # Preserve the retained device ID, policies and confirmed target.
            session.add(Event(event_type="identity_merged", device_mac=retained.mac,
                description=f"Manually linked {candidate.mac} to device {retained.id}: {reason}"[:512]))
            session.delete(candidate)

    def split(self, retained_id: int, alias_mac: str, *, name: str, confirmed: bool = False) -> Device:
        if not confirmed or not name.strip():
            raise ValidationError("Explicit confirmation and a new device name are required.")
        alias_mac = normalize_mac(alias_mac)
        with self.db.session() as session:
            alias = session.get(IdentityAlias, alias_mac)
            if not alias or alias.device_id != retained_id:
                raise ValidationError("Alias no longer belongs to this identity; reload devices.")
            if session.scalar(select(Device.id).where(Device.name == name.strip())):
                raise ValidationError("Device name already exists.")
            retained = session.get(Device, retained_id)
            device = Device(name=name.strip(), mac=alias_mac, online=False,
                            identity_note="Manually split identity; assign policies after verification.")
            session.add(device)
            session.flush()
            session.execute(update(AddressEvidence).where(AddressEvidence.device_id == retained_id,
                AddressEvidence.observed_mac == alias_mac).values(device_id=device.id))
            session.delete(alias)
            # Do not reassign ambiguous historical records or clone policies.
            retained.identity_conflict = True
            retained.identity_note = "Identity split: verify the retained address before enforcement."
            session.add(Event(event_type="identity_split", device_mac=alias_mac,
                              description=f"Split alias into device {device.id}; policy assignment is explicit."))
            session.expunge(device)
            return device

    def resolve_conflict(self, device_id: int, *, expected_ip: str | None, expected_mac: str, reason: str) -> None:
        with self.db.session() as session:
            device = session.get(Device, device_id)
            if not device or device.ip != expected_ip or device.mac != normalize_mac(expected_mac) or not reason.strip():
                raise ValidationError("Identity changed during review or review reason is missing.")
            if device.ip and session.scalar(select(Device.id).where(Device.id != device.id,
                    Device.ip == device.ip, Device.online.is_(True))):
                raise ValidationError("Another online identity still claims this address.")
            device.identity_conflict = False
            device.identity_note = reason.strip()[:512]
            session.add(Event(event_type="identity_resolved", device_mac=device.mac,
                              description=f"Identity reviewed: {reason}"[:512]))
