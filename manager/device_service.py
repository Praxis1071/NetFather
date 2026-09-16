"""Application-facing device management service for GTK4."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from core.database import Database
from manager.device_manager import DeviceManager
from models.device import Device


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

    def rename(self, current_name: str, new_name: str) -> DeviceSnapshot:
        self.manager.update_device(current_name, new_name=new_name)
        return self.refresh(new_name.strip())

    def update_metadata(
        self,
        name: str,
        *,
        ip: str | None = None,
        vendor: str | None = None,
        device_type: str | None = None,
    ) -> DeviceSnapshot:
        self.manager.update_device(name, ip=ip, vendor=vendor, device_type=device_type)
        return self.refresh(name)

    def delete(self, name: str) -> DeviceSnapshot:
        self.manager.delete_device(name)
        return self.refresh()

    def _emit(self) -> None:
        for callback in tuple(self._listeners):
            callback(self._snapshot)
