"""Presence -> discovery -> SQLite identity and audit history integration.

Only OS observation sources and timers are replaced. Managers, resolver,
discovery service and database transactions run normally without privilege.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from core.database import Database
from manager.event_manager import EventManager
from models.device_observation import DeviceObservationRecord
from network.discovery import DiscoveredHost, DiscoveryError
from network.live_presence import LivePresenceService
from network.presence import parse_neighbor_event


MAC = "AA:BB:CC:DD:EE:20"
IP = "192.168.1.20"


class ManualTimer:
    def __init__(self, interval, callback):
        self.callback = callback
        self.alive = False

    def start(self):
        self.alive = True

    def is_alive(self):
        return self.alive

    def cancel(self):
        self.alive = False

    def join(self):
        pass


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    clock = [datetime(2026, 10, 1, 12)]
    for module in ("manager.device_manager", "network.discovery_service", "network.identity"):
        monkeypatch.setattr(f"{module}.utc_now", lambda: clock[0])
    # Observations have their own default factory; stamp them using the same
    # clock so resolver and persistence grace thresholds are comparable.
    from network.discovery import observations_from_hosts

    def observations(hosts):
        from dataclasses import replace
        return [replace(item, observed_at=clock[0]) for item in observations_from_hosts(hosts)]

    monkeypatch.setattr("network.discovery_service.observations_from_hosts", observations)
    monkeypatch.setattr("network.live_presence.threading.Timer", ManualTimer)
    passive = [[]]
    active = [[]]

    def source(values):
        if isinstance(values[0], Exception):
            raise values[0]
        return values[0]

    monkeypatch.setattr("network.discovery._scan_linux", lambda _: source(passive))
    monkeypatch.setattr("network.discovery._scan_scapy", lambda *_: source(active))
    monkeypatch.setattr("network.discovery.infer_local_subnet", lambda: "192.168.1.0/24")
    db = Database(tmp_path / "presence.db")
    db.init_db()
    snapshots = []
    service = LivePresenceService(db, offline_after_seconds=45, on_reconciled=snapshots.append)
    service._stopped = False
    active[0] = [DiscoveredHost(IP, mac=MAC, source="active")]
    service._reconcile()
    active[0] = []
    yield service, clock, passive, active, snapshots
    service.stop()
    db.close()


def device(service):
    return service.device_manager.get_device_by_mac(MAC)


def event_count(service, kind):
    return sum(event.event_type == kind for event in EventManager(service.device_manager.db).list_events(limit=100))


@pytest.mark.parametrize("line", [
    f"Deleted {IP} dev eth0 lladdr {MAC}",
    f"{IP} dev eth0 lladdr {MAC} FAILED",
])
def test_removal_hint_obeys_grace_and_recovery_is_audited_once(runtime, line):
    service, clock, _, _, snapshots = runtime
    event = parse_neighbor_event(line)
    service._on_presence_event(event)
    assert device(service).online
    assert event_count(service, "device_offline") == 0

    clock[0] += timedelta(seconds=44)
    service._event_reconcile()
    assert device(service).online
    assert service.discovery.resolver.get(MAC).online

    clock[0] += timedelta(seconds=1)
    service._reconcile()
    assert not device(service).online
    assert not service.discovery.resolver.get(MAC).online
    assert snapshots[-1].offline_devices == 1
    service._reconcile()
    assert event_count(service, "device_offline") == 1

    service._on_presence_event(parse_neighbor_event(f"{IP} dev eth0 lladdr {MAC} REACHABLE"))
    service._on_presence_event(parse_neighbor_event(f"{IP} dev eth0 lladdr {MAC} REACHABLE"))
    assert device(service).online
    assert event_count(service, "device_online") == 1


def test_failed_cycle_preserves_identity_history_and_last_known_presence(runtime):
    service, clock, passive, active, snapshots = runtime
    original = device(service)
    with service.device_manager.db.session() as session:
        original_history = list(session.scalars(select(DeviceObservationRecord.id)))
    clock[0] += timedelta(seconds=60)
    passive[0] = DiscoveryError("ip timed out")
    active[0] = PermissionError("ARP requires privilege")
    service._reconcile()
    snapshot = snapshots[-1]
    assert not snapshot.complete and len(snapshot.warnings) == 2
    assert device(service).id == original.id
    assert device(service).ip == original.ip
    assert device(service).last_seen == original.last_seen
    assert device(service).online
    assert service.discovery.resolver.get(MAC).online
    assert event_count(service, "device_offline") == 0
    with service.device_manager.db.session() as session:
        assert list(session.scalars(select(DeviceObservationRecord.id))) == original_history

    passive[0] = []
    active[0] = []
    service._reconcile()
    assert snapshots[-1].complete
    assert not device(service).online
    assert event_count(service, "device_offline") == 1


def test_partial_cycle_updates_dhcp_target_without_expiring_absent_device(runtime):
    service, clock, passive, active, snapshots = runtime
    second_mac = "AA:BB:CC:DD:EE:21"
    active[0] = [DiscoveredHost("192.168.1.21", mac=second_mac, source="active")]
    service._reconcile()
    clock[0] += timedelta(seconds=60)
    passive[0] = DiscoveryError("neighbor table unavailable")
    active[0] = [DiscoveredHost("192.168.1.42", mac=MAC, source="active")]
    service._reconcile()
    assert not snapshots[-1].complete
    assert device(service).ip == "192.168.1.42"
    assert service.device_manager.get_device_by_mac(second_mac).online
    assert service.discovery.resolver.get(second_mac).online
    assert event_count(service, "device_ip_changed") == 1
    assert event_count(service, "device_offline") == 0


def test_auto_registration_setting_still_allows_existing_device_updates(runtime):
    service, _, _, active, snapshots = runtime
    service.auto_register = False
    active[0] = [
        DiscoveredHost("192.168.1.42", mac=MAC, source="active"),
        DiscoveredHost("192.168.1.21", mac="AA:BB:CC:DD:EE:21", source="active"),
    ]
    service._reconcile()
    assert snapshots[-1].new_devices == 0
    assert device(service).ip == "192.168.1.42"
    assert service.device_manager.get_device_by_mac("AA:BB:CC:DD:EE:21") is None


def test_no_presence_write_or_callback_after_stop(runtime):
    service, _, _, _, snapshots = runtime
    service.stop()
    before = len(snapshots)
    service._on_presence_event(parse_neighbor_event(f"192.168.1.42 dev eth0 lladdr {MAC} REACHABLE"))
    service._reconcile()
    assert device(service).ip == IP
    assert len(snapshots) == before


def test_persistence_failure_does_not_expire_runtime_identity(runtime, monkeypatch):
    service, clock, _, _, snapshots = runtime
    clock[0] += timedelta(seconds=60)

    def failed(*args, **kwargs):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(service.device_manager, "reconcile_discovery", failed)
    service._reconcile()
    assert snapshots[-1].error == "database unavailable"
    assert not snapshots[-1].complete
    assert service.discovery.resolver.get(MAC).online
    assert device(service).online
