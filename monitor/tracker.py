"""Live device presence tracker."""
from __future__ import annotations
from dataclasses import dataclass
from core.config import Config
from core.database import Database
from manager.device_manager import DeviceManager
from network.discovery import DiscoveredHost, scan_network

@dataclass(frozen=True)
class TrackerResult:
    hosts: tuple[DiscoveredHost, ...]
    new_devices: int
    updated_devices: int
    offline_devices: int

class DeviceTracker:
    def __init__(self, db: Database, config: Config) -> None:
        self.db, self.config = db, config
    def poll_once(self, *, active: bool = False) -> TrackerResult:
        d = self.config.discovery
        mode = d.mode if active else "passive"
        hosts = scan_network(
            timeout_seconds=self.config.network.scan_timeout_seconds,
            mode=mode,
            subnet=d.subnet or None,
            hostname_resolution=d.hostname_resolution if active else False,
            vendor_detection=d.vendor_detection,
            os_detection=d.os_detection if active else False,
            active_timeout_seconds=d.active_timeout_seconds,
        )
        new_count, updated, offline = DeviceManager(self.db).reconcile_discovery(
            hosts, auto_register=d.auto_register,
            offline_after_seconds=d.offline_after_seconds,
        )
        return TrackerResult(tuple(hosts), new_count, updated, offline)
