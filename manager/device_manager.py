"""
Device manager.

Cihazlar üzerinde CRUD işlemlerini yürütür. FAZ 1'de sadece temel
veritabanı işlemlerini içerir; ağ keşfiyle entegrasyon FAZ 2/3'te eklenecektir.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select

from core.database import Database
from core.exceptions import DeviceNotFoundError
from core.logger import get_logger
from models.device import Device

log = get_logger("device_manager")


class DeviceManager:
    """Cihaz kayıtlarını yönetir."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def add_device(
        self,
        name: str,
        mac: str,
        ip: str | None = None,
        vendor: str | None = None,
        device_type: str = "unknown",
    ) -> Device:
        """Yeni bir cihaz kaydeder."""
        with self.db.session() as session:
            device = Device(
                name=name,
                mac=mac.upper(),
                ip=ip,
                vendor=vendor,
                device_type=device_type,
                created_at=dt.datetime.utcnow(),
            )
            session.add(device)
            session.flush()
            log.info("Cihaz eklendi: %s (%s)", name, mac)
            session.refresh(device)
            session.expunge(device)
            return device

    def list_devices(self) -> list[Device]:
        """Tüm kayıtlı cihazları döndürür."""
        with self.db.session() as session:
            devices = list(session.scalars(select(Device)).all())
            for d in devices:
                session.expunge(d)
            return devices

    def get_device_by_name(self, name: str) -> Device:
        """İsme göre cihaz döndürür, bulunamazsa hata fırlatır."""
        with self.db.session() as session:
            device = session.scalar(select(Device).where(Device.name == name))
            if device is None:
                raise DeviceNotFoundError(f"Cihaz bulunamadı: {name}")
            session.expunge(device)
            return device

    def get_device_by_mac(self, mac: str) -> Device | None:
        """MAC adresine göre cihaz döndürür, yoksa None."""
        with self.db.session() as session:
            device = session.scalar(select(Device).where(Device.mac == mac.upper()))
            if device is not None:
                session.expunge(device)
            return device

    def update_last_seen(self, mac: str, ip: str | None = None) -> None:
        """Cihazın son görülme zamanını (ve varsa IP'sini) günceller."""
        with self.db.session() as session:
            device = session.scalar(select(Device).where(Device.mac == mac.upper()))
            if device is None:
                raise DeviceNotFoundError(f"Cihaz bulunamadı: {mac}")
            device.last_seen = dt.datetime.utcnow()
            if ip:
                device.ip = ip

    def delete_device(self, name: str) -> None:
        """İsme göre cihazı siler."""
        with self.db.session() as session:
            device = session.scalar(select(Device).where(Device.name == name))
            if device is None:
                raise DeviceNotFoundError(f"Cihaz bulunamadı: {name}")
            session.delete(device)
            log.info("Cihaz silindi: %s", name)
