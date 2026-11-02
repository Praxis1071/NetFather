"""Reusable profile CRUD, explicit assignment and audit history."""
import json
from sqlalchemy import select
from core.database import Database
from core.exceptions import ValidationError, ProfileNotFoundError
from models.device import Device
from models.event import Event
from models.policy_group import PolicyGroup, ProfileAssignment
from manager.profile_manager import ProfileManager


class GroupManager:
    def __init__(self, db: Database):
        self.db = db

    @staticmethod
    def require(session, profile_id):
        profile = session.get(PolicyGroup, profile_id)
        if profile is None:
            raise ProfileNotFoundError(f"Profile not found: {profile_id}")
        return profile

    def list_profiles(self, device_id=None):
        with self.db.session() as session:
            query = select(PolicyGroup).order_by(PolicyGroup.name, PolicyGroup.id)
            if device_id is not None:
                query = query.join(ProfileAssignment).where(ProfileAssignment.device_id == device_id)
            result = list(session.scalars(query))
            for item in result:
                session.expunge(item)
            return result

    def save(self, name, internet_mode, *, profile_id=None):
        name = ProfileManager._validate_name(name)
        mode = ProfileManager._validate_mode(internet_mode)
        with self.db.session() as session:
            existing = session.scalar(select(PolicyGroup).where(PolicyGroup.name == name))
            if existing and existing.id != profile_id:
                raise ValidationError("A reusable profile with this name already exists.")
            profile = self.require(session, profile_id) if profile_id else PolicyGroup()
            profile.name, profile.internet_mode = name, mode
            session.add(profile)
            session.flush()
            session.add(Event(event_type="profile_changed" if profile_id else "profile_created",
                metadata_json=json.dumps({"profile_id": profile.id}), description=f"Reusable profile {profile.id}: {name} ({mode})"))
            session.expunge(profile)
            return profile

    def assignments(self, profile_id):
        with self.db.session() as session:
            self.require(session, profile_id)
            result = list(session.scalars(select(Device).join(ProfileAssignment).where(ProfileAssignment.profile_id == profile_id)))
            for item in result:
                session.expunge(item)
            return result

    def assign(self, profile_id, device_id):
        with self.db.session() as session:
            profile = self.require(session, profile_id)
            device = session.get(Device, device_id)
            if device is None:
                raise ValidationError("Device no longer exists.")
            existing = session.get(ProfileAssignment, device_id)
            if existing:
                if existing.profile_id == profile_id:
                    return
                raise ValidationError("Unassign the existing reusable profile before assigning another.")
            session.add(ProfileAssignment(profile_id=profile_id, device_id=device_id))
            session.add(Event(event_type="profile_changed", device_mac=device.mac,
                metadata_json=json.dumps({"profile_id": profile.id}), description=f"Assigned reusable profile {profile.id}: {profile.name}"))

    def unassign(self, profile_id, device_id):
        with self.db.session() as session:
            assignment = session.get(ProfileAssignment, device_id)
            if not assignment or assignment.profile_id != profile_id:
                raise ValidationError("Assignment changed during review; reload profiles.")
            device = session.get(Device, device_id)
            session.delete(assignment)
            session.add(Event(event_type="profile_changed", device_mac=device.mac,
                              metadata_json=json.dumps({"profile_id": profile_id}), description=f"Unassigned reusable profile {profile_id}"))

    def delete(self, profile_id):
        with self.db.session() as session:
            profile = self.require(session, profile_id)
            if session.scalar(select(ProfileAssignment.device_id).where(ProfileAssignment.profile_id == profile_id)):
                raise ValidationError("Unassign all devices before deleting this profile.")
            session.add(Event(event_type="profile_deleted", metadata_json=json.dumps({"profile_id": profile.id}), description=f"Reusable profile {profile.id}: {profile.name}"))
            session.delete(profile)

    def history(self, profile_id):
        with self.db.session() as session:
            records = list(session.scalars(select(Event).where(Event.metadata_json == json.dumps({"profile_id": profile_id}))
                .order_by(Event.timestamp.desc(), Event.id.desc()).limit(50)))
            for item in records:
                session.expunge(item)
            return records
