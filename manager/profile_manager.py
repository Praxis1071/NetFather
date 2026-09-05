"""CRUD operations for device access profiles."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from core.database import Database
from core.exceptions import (
    DuplicateProfileError,
    ProfileNotFoundError,
    ValidationError,
)
from core.logger import get_logger
from manager.device_manager import DeviceManager
from models.profile import Profile
from models.event import Event
from models.device import Device

log = get_logger("profile_manager")

VALID_INTERNET_MODES = frozenset({"unrestricted", "controlled", "blocked"})


class ProfileManager:
    """Manage profiles attached to registered devices."""

    def __init__(self, db: Database) -> None:
        self.db = db

    @staticmethod
    def _validate_name(name: str) -> str:
        cleaned = name.strip()
        if not cleaned:
            raise ValidationError("Profil adı boş olamaz.")
        if len(cleaned) > 128:
            raise ValidationError("Profil adı en fazla 128 karakter olabilir.")
        return cleaned

    @staticmethod
    def _validate_mode(mode: str) -> str:
        normalized = mode.strip().lower()
        if normalized not in VALID_INTERNET_MODES:
            values = ", ".join(sorted(VALID_INTERNET_MODES))
            raise ValidationError(f"Geçersiz internet modu: {mode!r}. Geçerli değerler: {values}")
        return normalized

    def create_profile(self, device_name: str, name: str, internet_mode: str = "unrestricted") -> Profile:
        profile_name = self._validate_name(name)
        mode = self._validate_mode(internet_mode)

        with self.db.session() as session:
            device = DeviceManager._require_by_name(session, device_name)
            duplicate = session.scalar(
                select(Profile).where(
                    Profile.device_id == device.id,
                    Profile.name == profile_name,
                )
            )
            if duplicate is not None:
                raise DuplicateProfileError(
                    f"{device.name!r} cihazında {profile_name!r} adlı profil zaten var."
                )

            profile = Profile(device_id=device.id, name=profile_name, internet_mode=mode)
            session.add(profile)
            session.add(Event(event_type="profile_created", description=f"Profile {profile_name} ({mode}) created for {device.name}", device_mac=device.mac))
            session.flush()
            session.refresh(profile)
            # Attach the already-loaded device before expunging so callers can
            # safely display ``profile.device.name`` outside the session.
            profile.device = device
            session.expunge(profile)
            log.info("Profil oluşturuldu: %s -> %s", device.name, profile_name)
            return profile

    def list_profiles(self, device_name: str | None = None) -> list[Profile]:
        with self.db.session() as session:
            statement = select(Profile).options(joinedload(Profile.device)).order_by(Profile.name)
            if device_name is not None:
                device = DeviceManager._require_by_name(session, device_name)
                statement = statement.where(Profile.device_id == device.id)
            profiles = list(session.scalars(statement).all())
            for profile in profiles:
                session.expunge(profile)
            return profiles

    def get_profile(self, profile_id: int) -> Profile:
        with self.db.session() as session:
            profile = session.scalar(
                select(Profile).options(joinedload(Profile.device)).where(Profile.id == profile_id)
            )
            if profile is None:
                raise ProfileNotFoundError(f"Profil bulunamadı: id={profile_id}")
            session.expunge(profile)
            return profile

    def set_mode(self, profile_id: int, internet_mode: str) -> Profile:
        mode = self._validate_mode(internet_mode)
        with self.db.session() as session:
            profile = session.get(Profile, profile_id)
            if profile is None:
                raise ProfileNotFoundError(f"Profil bulunamadı: id={profile_id}")
            profile.internet_mode = mode
            device = session.get(Device, profile.device_id)
            session.add(Event(event_type="profile_changed", description=f"Profile {profile_id} mode -> {mode}", device_mac=device.mac if device else None))
            session.flush()
            session.refresh(profile)
            session.expunge(profile)
            log.info("Profil modu değiştirildi: id=%s mode=%s", profile_id, mode)
            return profile

    def delete_profile(self, profile_id: int) -> None:
        with self.db.session() as session:
            profile = session.get(Profile, profile_id)
            if profile is None:
                raise ProfileNotFoundError(f"Profil bulunamadı: id={profile_id}")
            device = session.get(Device, profile.device_id)
            session.add(Event(event_type="profile_deleted", description=f"Profile {profile_id} deleted", device_mac=device.mac if device else None))
            session.delete(profile)
            log.info("Profil silindi: id=%s", profile_id)
