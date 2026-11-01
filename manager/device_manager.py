"""
Device manager.

Kayıtlı cihazların CRUD işlemlerini, discovery sonucundan bilinen cihazların
last_seen/IP/vendor senkronizasyonunu ve alan güncellemelerini yürütür.
"""

from __future__ import annotations

from collections.abc import Iterable
import re
import datetime as dt
import json
from typing import TYPE_CHECKING

from sqlalchemy import desc, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.database import Database
from core.exceptions import DeviceNotFoundError, DuplicateDeviceError, ValidationError
from core.logger import get_logger
from core.time_utils import utc_now
from models.device import Device
from models.device_observation import DeviceObservationRecord
from models.event import Event
from models.network_evidence import AddressEvidence, IdentityAlias, ServiceEvidence
from network.device import lookup_vendor, normalize_mac

if TYPE_CHECKING:
    from network.discovery import DiscoveredHost

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
        normalized = normalize_mac(mac)
        device = session.scalar(select(Device).where(Device.mac == normalized))
        alias = session.get(IdentityAlias, normalized) if device is None else None
        return session.get(Device, alias.device_id) if alias else device

    @staticmethod
    def _check_address_conflicts(session: Session, extra_claims=()) -> None:
        claims: dict[str, dict[int, Device]] = {}
        for device in session.scalars(select(Device).where(Device.online.is_(True))):
            if device.ip:
                claims.setdefault(device.ip, {})[device.id] = device
        for ip, mac in extra_claims:
            device = DeviceManager._find_by_mac(session, mac)
            if device:
                claims.setdefault(ip, {})[device.id] = device
        for address, devices in claims.items():
            if len(devices) < 2:
                continue
            for device in devices.values():
                if not device.identity_conflict:
                    session.add(Event(event_type="identity_conflict", device_mac=device.mac,
                        severity="warning", description=f"Multiple online identities claim {address}; enforcement excluded."))
                device.identity_conflict = True
                device.identity_note = f"Multiple online identities claim {address}; review required."

    @staticmethod
    def _record_observation(session: Session, device: Device, host: "DiscoveredHost", observed_at: dt.datetime) -> None:
        """Persist a new identity observation without duplicating unchanged polls."""
        if host.ip and host.presence_confirmed:
            path = session.scalar(select(AddressEvidence).where(AddressEvidence.device_id == device.id,
                AddressEvidence.ip == host.ip, AddressEvidence.interface == (host.interface or "")))
            if path is None:
                path = AddressEvidence(device_id=device.id, ip=host.ip, interface=host.interface or "",
                    observed_mac=normalize_mac(host.mac), source=host.source,
                    first_seen=observed_at, last_seen=observed_at)
                session.add(path)
            else:
                path.last_seen = observed_at
                path.observed_mac = normalize_mac(host.mac)
                path.source = host.source
        if host.scan_method == "nmap":
            tcp, udp, services = map(json.dumps, (host.open_tcp_ports, host.open_udp_ports, host.services))
            latest_service = session.scalar(select(ServiceEvidence).where(ServiceEvidence.device_id == device.id,
                ServiceEvidence.ip == host.ip).order_by(ServiceEvidence.observed_at.desc(), ServiceEvidence.id.desc()).limit(1))
            if latest_service is None or (latest_service.tcp_ports, latest_service.udp_ports, latest_service.services) != (tcp, udp, services):
                session.add(ServiceEvidence(device_id=device.id, ip=host.ip, observed_at=observed_at,
                    tcp_ports=tcp, udp_ports=udp, services=services))
        source = (getattr(host, "source", None) or "unknown").strip().lower() or "unknown"
        ip = getattr(host, "ip", None)
        latest = session.scalar(
            select(DeviceObservationRecord)
            .where(
                DeviceObservationRecord.device_id == device.id,
                DeviceObservationRecord.ip == ip,
                DeviceObservationRecord.source == source,
            )
            .order_by(desc(DeviceObservationRecord.observed_at))
            .limit(1)
        )
        confidence = 0.95 if "active" in source else 0.8
        if "deep" in source:
            confidence = min(1.0, confidence + 0.03)
        if getattr(host, "hostname", None):
            confidence = min(1.0, confidence + 0.03)
        if getattr(host, "vendor", None):
            confidence = min(1.0, confidence + 0.02)

        if latest is not None:
            same_metadata = all(
                getattr(latest, field) == getattr(host, field, None)
                for field in ("interface", "hostname", "vendor", "device_type", "os_hint")
            )
            if same_metadata:
                return

        session.add(
            DeviceObservationRecord(
                device_id=device.id,
                ip=ip,
                interface=getattr(host, "interface", None),
                hostname=getattr(host, "hostname", None),
                vendor=getattr(host, "vendor", None),
                device_type=getattr(host, "device_type", None),
                os_hint=getattr(host, "os_hint", None),
                source=source,
                confidence=confidence,
                observed_at=observed_at,
            )
        )

    @staticmethod
    def _record_manual_observation(session: Session, device: Device, ip: str, observed_at: dt.datetime) -> None:
        """Persist a user-supplied IP observation when the managed address changes."""
        latest = session.scalar(
            select(DeviceObservationRecord)
            .where(
                DeviceObservationRecord.device_id == device.id,
                DeviceObservationRecord.ip == ip,
                DeviceObservationRecord.source == "manual",
            )
            .order_by(desc(DeviceObservationRecord.observed_at))
            .limit(1)
        )
        if latest is None:
            session.add(
                DeviceObservationRecord(
                    device_id=device.id,
                    ip=ip,
                    source="manual",
                    confidence=1.0,
                    observed_at=observed_at,
                )
            )

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
        except (TypeError, ValueError, AttributeError) as exc:  # savunmacı: mac None/beklenmedik tip
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
                    vendor=vendor or lookup_vendor(normalized_mac),
                    device_type=device_type,
                    online=False,
                    auto_registered=False,
                    created_at=utc_now(),
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

            if ip:
                self._record_manual_observation(session, device, ip, utc_now())
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
        try:
            normalized = normalize_mac(mac)
        except (TypeError, ValueError, AttributeError) as exc:
            raise ValidationError(f"Geçersiz MAC adresi: {mac!r}") from exc
        with self.db.session() as session:
            device = self._find_by_mac(session, normalized)
            if device is not None:
                session.expunge(device)
            return device

    def update_last_seen(self, mac: str, ip: str | None = None) -> None:
        """
        Cihazın son görülme zamanını (ve varsa IP'sini) günceller.

        Raises:
            DeviceNotFoundError: Belirtilen MAC'e sahip cihaz yoksa.
        """
        try:
            normalized = normalize_mac(mac)
        except (TypeError, ValueError, AttributeError) as exc:
            raise ValidationError(f"Geçersiz MAC adresi: {mac!r}") from exc
        with self.db.session() as session:
            device = self._find_by_mac(session, normalized)
            if device is None:
                raise DeviceNotFoundError(f"Cihaz bulunamadı: {normalized}")
            now = utc_now()
            device.last_seen = now
            if ip and device.ip != ip:
                previous_ip = device.ip
                device.ip = ip
                self._record_manual_observation(session, device, ip, now)
                if previous_ip:
                    session.add(Event(event_type="device_ip_changed", description=f"{device.name} IP changed: {previous_ip} -> {ip}", device_mac=device.mac))

    def update_device(
        self,
        name: str,
        *,
        new_name: str | None = None,
        mac: str | None = None,
        ip: str | None = None,
        vendor: str | None = None,
        device_type: str | None = None,
    ) -> Device:
        """Update editable fields of an existing device.

        ``None`` means "leave unchanged" for optional arguments.  Name and
        MAC uniqueness are checked before the update is committed.
        """
        with self.db.session() as session:
            device = self._require_by_name(session, name)

            if new_name is not None:
                cleaned_name = new_name.strip()
                if not cleaned_name:
                    raise ValidationError("Cihaz ismi boş olamaz.")
                existing = self._find_by_name(session, cleaned_name)
                if existing is not None and existing.id != device.id:
                    raise DuplicateDeviceError(
                        f"Bu isimde bir cihaz zaten kayıtlı: {cleaned_name!r}"
                    )
                device.name = cleaned_name

            if mac is not None:
                try:
                    normalized_mac = normalize_mac(mac)
                except (TypeError, ValueError, AttributeError) as exc:
                    raise ValidationError(f"Geçersiz MAC adresi: {mac!r}") from exc
                existing = self._find_by_mac(session, normalized_mac)
                if existing is not None and existing.id != device.id:
                    raise DuplicateDeviceError(
                        f"Bu MAC adresine sahip bir cihaz zaten kayıtlı: {normalized_mac}"
                    )
                device.mac = normalized_mac

            if ip is not None:
                new_ip = ip.strip() or None
                if new_ip != device.ip and new_ip:
                    self._record_manual_observation(session, device, new_ip, utc_now())
                    if device.ip:
                        session.add(Event(event_type="device_ip_changed", description=f"{device.name} IP changed: {device.ip} -> {new_ip}", device_mac=device.mac))
                device.ip = new_ip
            if vendor is not None:
                device.vendor = vendor.strip() or None
            if device_type is not None:
                cleaned_type = device_type.strip().lower()
                if not cleaned_type:
                    raise ValidationError("Cihaz tipi boş olamaz.")
                device.device_type = cleaned_type

            try:
                session.flush()
            except IntegrityError as exc:
                raise DuplicateDeviceError(
                    "Cihaz güncellenemedi; isim veya MAC başka bir kayıtla çakışıyor."
                ) from exc
            session.refresh(device)
            session.add(Event(event_type="device_updated", description=f"Device updated: {device.name}", device_mac=device.mac))
            session.expunge(device)
            log.info("Cihaz güncellendi: %s (%s)", device.name, device.mac)
            return device

    def update_presence(self, mac: str, *, online: bool, ip: str | None = None) -> bool:
        """Apply a low-latency neighbor presence transition to a known device."""
        try:
            normalized = normalize_mac(mac)
        except (TypeError, ValueError, AttributeError):
            return False
        with self.db.session() as session:
            device = self._find_by_mac(session, normalized)
            if device is None:
                return False
            now = utc_now()
            if online:
                was_online = device.online
                previous_ip = device.ip
                device.online = True
                device.last_seen = now
                if ip and previous_ip != ip:
                    device.ip = ip
                    session.add(Event(
                        event_type="device_ip_changed",
                        description=f"{device.name} IP changed: {previous_ip} -> {ip}",
                        device_mac=device.mac,
                    ))
                    session.add(DeviceObservationRecord(
                        device_id=device.id,
                        ip=ip,
                        source="neighbor",
                        confidence=0.9,
                        observed_at=now,
                    ))
                if not was_online:
                    session.add(Event(
                        event_type="device_online",
                        description=f"{device.name} ağa katıldı",
                        device_mac=device.mac,
                    ))
                self._check_address_conflicts(session)
            elif device.online:
                device.online = False
                session.add(Event(
                    event_type="device_offline",
                    description=f"{device.name} ağdan ayrıldı",
                    device_mac=device.mac,
                ))
            return True

    def sync_discovered_hosts(self, hosts: Iterable["DiscoveredHost"]) -> int:
        """Refresh ``last_seen``/IP/vendor for already-registered discovered MACs.

        Unknown devices are never inserted automatically.  The return value is
        the number of registered devices that were updated.
        """
        updated = 0
        seen_macs: set[str] = set()
        now = utc_now()
        with self.db.session() as session:
            for host in hosts:
                if not host.mac or not host.presence_confirmed:
                    continue
                try:
                    normalized_mac = normalize_mac(host.mac)
                except (TypeError, ValueError, AttributeError):
                    continue
                if normalized_mac in seen_macs:
                    continue
                seen_macs.add(normalized_mac)

                device = self._find_by_mac(session, normalized_mac)
                if device is None:
                    continue
                was_online = bool(device.online)
                previous_ip = device.ip
                device.last_seen = now
                device.online = True
                if host.ip:
                    device.ip = host.ip
                DeviceManager._record_observation(session, device, host, now)
                if host.ip and previous_ip and previous_ip != host.ip:
                    session.add(Event(event_type="device_ip_changed", description=f"{device.name} IP changed: {previous_ip} -> {host.ip}", device_mac=device.mac))
                if host.vendor:
                    device.vendor = host.vendor
                if getattr(host, "hostname", None):
                    device.hostname = host.hostname
                if getattr(host, "device_type", None):
                    device.device_type = host.device_type
                if getattr(host, "os_hint", None):
                    device.os_hint = host.os_hint
                if not was_online:
                    session.add(Event(event_type="device_online", description=f"{device.name} ağa katıldı", device_mac=device.mac))
                updated += 1

        if updated:
            log.info("Discovery ile %s kayıtlı cihaz güncellendi", updated)
        return updated

    @staticmethod
    def _auto_name(host: "DiscoveredHost", existing_names: set[str]) -> str:
        base = (getattr(host, "hostname", None) or getattr(host, "device_type", None) or
                getattr(host, "vendor", None) or "Device")
        base = re.sub(r"[^A-Za-z0-9_. -]+", "", str(base)).strip()[:80] or "Device"
        suffix = (host.mac or host.ip).replace(":", "").replace(".", "")[-6:]
        candidate = f"{base}-{suffix}"
        n = 2
        while candidate in existing_names:
            candidate = f"{base}-{suffix}-{n}"; n += 1
        existing_names.add(candidate)
        return candidate

    def reconcile_discovery(self, hosts: Iterable["DiscoveredHost"], *, auto_register: bool = True,
                            offline_after_seconds: int = 45,
                            mark_missing_offline: bool = True) -> tuple[int, int, int]:
        """Persist discovery, auto-register new devices and update online/offline state.

        Returns ``(new_devices, updated_devices, offline_devices)``. Devices are
        marked offline only after the grace period, preventing a single missed
        neighbour-cache sample from creating false leave events.
        Incomplete scans must set ``mark_missing_offline=False``; their positive
        observations remain useful but absence is not evidence of departure.
        Cache-only observations do not refresh last_seen, select a current IP,
        auto-register a device, or extend the grace period.
        """
        from network.identity import preferred_address_key
        now = utc_now()
        new_count = updated = offline_count = 0
        seen: set[str] = set()
        with self.db.session() as session:
            names = set(session.scalars(select(Device.name)).all())
            groups: dict[str, list] = {}
            for host in hosts:
                if not host.mac or not host.presence_confirmed:
                    continue
                try:
                    mac = normalize_mac(host.mac)
                except (TypeError, ValueError, AttributeError):
                    continue
                known = self._find_by_mac(session, mac)
                groups.setdefault(known.mac if known else mac, []).append(host)
            for mac, paths in groups.items():
                seen.add(mac)
                device = self._find_by_mac(session, mac)
                host = min(paths, key=lambda path: (
                    preferred_address_key(path.ip), path.ip != (device.ip if device else None),
                    path.ip, path.interface or ""))
                if device is None:
                    if not auto_register:
                        continue
                    device = Device(name=self._auto_name(host, names), mac=mac, ip=host.ip,
                        vendor=host.vendor or lookup_vendor(mac), device_type=host.device_type or "unknown",
                        hostname=host.hostname, os_hint=host.os_hint, online=True,
                        auto_registered=True, created_at=now, last_seen=now)
                    session.add(device)
                    session.flush()
                    new_count += 1
                    session.add(Event(event_type="device_discovered", description=f"New device: {device.name}", device_mac=mac))
                else:
                    was_online, previous_ip = bool(device.online), device.ip
                    device.ip = host.ip or device.ip
                    if host.ip and previous_ip and previous_ip != host.ip:
                        session.add(Event(event_type="device_ip_changed",
                            description=f"{device.name} IP changed: {previous_ip} -> {host.ip}", device_mac=mac))
                    device.vendor = host.vendor or device.vendor
                    device.hostname = host.hostname or device.hostname
                    device.os_hint = host.os_hint or device.os_hint
                    if host.device_type and host.device_type != "unknown":
                        device.device_type = host.device_type
                    device.last_seen, device.online = now, True
                    updated += 1
                    if not was_online:
                        session.add(Event(event_type="device_online", description=f"{device.name} online", device_mac=mac))
                for path in paths:
                    self._record_observation(session, device, path, now)
            if mark_missing_offline:
                threshold = now - dt.timedelta(seconds=max(1, offline_after_seconds))
                for device in session.scalars(select(Device).where(Device.online.is_(True))).all():
                    if device.mac not in seen and device.last_seen is not None and device.last_seen <= threshold:
                        device.online = False
                        offline_count += 1
                        session.add(Event(event_type="device_offline", description=f"{device.name} offline", device_mac=device.mac))
            self._check_address_conflicts(session, ((path.ip, mac) for mac, paths in groups.items() for path in paths))
        return new_count, updated, offline_count

    def delete_device(self, name: str, *, expected_id: int | None = None) -> None:
        """
        İsme göre cihazı siler.

        Raises:
            DeviceNotFoundError: Belirtilen isimde cihaz yoksa.
        """
        with self.db.session() as session:
            device = self._require_by_name(session, name)
            if expected_id is not None and device.id != expected_id:
                raise ValidationError("Device changed during confirmation; reload the inventory.")
            session.add(Event(event_type="device_deleted", description=f"Device deleted: {device.name}", device_mac=device.mac))
            session.delete(device)
            log.info("Cihaz silindi: %s", name)
