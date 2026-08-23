"""
Device manager.

Cihazlar üzerinde CRUD işlemlerini yürütür. FAZ 1'de sadece temel
veritabanı işlemlerini içerir; ağ keşfiyle entegrasyon FAZ 2/3'te eklenecektir.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.database import Database
from core.exceptions import DeviceNotFoundError, DuplicateDeviceError, ValidationError
from core.logger import get_logger
from models.device import Device
from network.device import normalize_mac

log = get_logger("device_manager")


class DeviceManager:
    """Cihaz kayıtlarını yönetir."""

    def __init__(self, db: Database) -> None:
        self.db = db

    # -- iç yardımcılar ----------------------------------------------------

    @staticmethod
    def _find_by_name(session: Session, name: str) -> Device | None:
        return session.scalar(select(Device).where(Device.name == name.strip()))

    @staticmethod
    def _find_by_mac(session: Session, mac: str) -> Device | None:
        return session.scalar(select(Device).where(Device.mac == normalize_mac(mac)))

    @staticmethod
    def _require_by_name(session: Session, name: str) -> Device:
        device = DeviceManager._find_by_name(session, name)
        if device is None:
            raise DeviceNotFoundError(f"Cihaz bulunamadı: {name!r}")
        return device

    # -- genel API -----------------------------------------------------------

    def add_device(
        self,
        name: str,
        mac: str,
        ip: str | None = None,
        vendor: str | None = None,
        device_type: str = "unknown",
    ) -> Device:
        """
        Yeni bir cihaz kaydeder.

        Args:
            name: Cihazın görünen ismi (benzersiz olmalıdır).
            mac: Cihazın MAC adresi (benzersiz olmalıdır; ':' veya '-'
                ayraçlı kabul edilir, saklanmadan önce normalize edilir).
            ip: Cihazın (varsa) bilinen IP adresi.
            vendor: Cihazın üretici bilgisi.
            device_type: Cihaz tipi (ör. laptop, phone, tablet, iot).

        Returns:
            Oluşturulan Device kaydı.

        Raises:
            DuplicateDeviceError: Aynı isim veya MAC ile kayıtlı bir cihaz
                zaten varsa.
            ValidationError: İsim boşsa veya MAC formatı geçersizse.
        """
        try:
            normalized_mac = normalize_mac(mac)
        except (TypeError, AttributeError) as exc:  # savunmacı: mac None/beklenmedik tip
            raise ValidationError(f"Geçersiz MAC adresi: {mac!r}") from exc

        with self.db.session() as session:
            if self._find_by_name(session, name) is not None:
                raise DuplicateDeviceError(f"Bu isimde bir cihaz zaten kayıtlı: {name!r}")
            if self._find_by_mac(session, normalized_mac) is not None:
                raise DuplicateDeviceError(
                    f"Bu MAC adresine sahip bir cihaz zaten kayıtlı: {normalized_mac}"
                )

            try:
                device = Device(
                    name=name,
                    mac=normalized_mac,
                    ip=ip,
                    vendor=vendor,
                    device_type=device_type,
                    created_at=dt.datetime.utcnow(),
                )
            except ValueError as exc:
                # models.device.Device alan doğrulayıcılarından (validates)
                # gelen hatalar (boş isim, geçersiz MAC formatı vb.)
                raise ValidationError(str(exc)) from exc

            session.add(device)

            try:
                session.flush()
            except IntegrityError as exc:
                # Eşzamanlı bir ekleme yarış durumuna (race condition) karşı
                # son bir güvenlik ağı; normal akışta yukarıdaki ön kontroller
                # bu duruma düşülmesini zaten engeller.
                raise DuplicateDeviceError(
                    f"Cihaz eklenemedi, MAC veya isim çakışması: {exc}"
                ) from exc

            session.refresh(device)
            session.expunge(device)
            log.info("Cihaz eklendi: %s (%s)", device.name, device.mac)
            return device

    def list_devices(self) -> list[Device]:
        """Tüm kayıtlı cihazları isme göre sıralı şekilde döndürür."""
        with self.db.session() as session:
            devices = list(session.scalars(select(Device).order_by(Device.name)).all())
            for device in devices:
                session.expunge(device)
            return devices

    def get_device_by_name(self, name: str) -> Device:
        """
        İsme göre cihaz döndürür.

        Raises:
            DeviceNotFoundError: Belirtilen isimde cihaz yoksa.
        """
        with self.db.session() as session:
            device = self._require_by_name(session, name)
            session.expunge(device)
            return device

    def get_device_by_mac(self, mac: str) -> Device | None:
        """MAC adresine göre cihaz döndürür, kayıt yoksa None döner."""
        with self.db.session() as session:
            device = self._find_by_mac(session, mac)
            if device is not None:
                session.expunge(device)
            return device

    def update_last_seen(self, mac: str, ip: str | None = None) -> None:
        """
        Cihazın son görülme zamanını (ve varsa IP'sini) günceller.

        Raises:
            DeviceNotFoundError: Belirtilen MAC'e sahip cihaz yoksa.
        """
        with self.db.session() as session:
            device = self._find_by_mac(session, mac)
            if device is None:
                raise DeviceNotFoundError(f"Cihaz bulunamadı: {normalize_mac(mac)}")
            device.last_seen = dt.datetime.utcnow()
            if ip:
                device.ip = ip

    def delete_device(self, name: str) -> None:
        """
        İsme göre cihazı siler.

        Raises:
            DeviceNotFoundError: Belirtilen isimde cihaz yoksa.
        """
        with self.db.session() as session:
            device = self._require_by_name(session, name)
            session.delete(device)
            log.info("Cihaz silindi: %s", name)
