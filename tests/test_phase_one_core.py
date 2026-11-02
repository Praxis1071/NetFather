"""Phase I acceptance: real SQLite transactions, identity review and cancellation."""
from __future__ import annotations

from concurrent.futures import CancelledError
from datetime import datetime, timedelta
import subprocess
import sys
import threading
import time

import pytest
from sqlalchemy import select

from core.database import Database
from core.exceptions import ValidationError
from core.operations import CancellationToken, run_process
from manager.device_manager import DeviceManager
from manager.event_manager import EventManager
from manager.identity_manager import IdentityManager
from manager.policy_engine import PolicyEngine
from manager.profile_manager import ProfileManager
from models.event import Event
from models.network_evidence import AddressEvidence, ScanRecord, ServiceEvidence
from network.discovery import DiscoveredHost, DiscoveryReport, _merge_discovery
from network.discovery_service import DiscoveryService
from network.enrichment import enrich_leases, parse_leases


@pytest.fixture
def db(tmp_path):
    database = Database(tmp_path / "phase-one.db")
    database.init_db()
    yield database
    database.close()


def host(ip="192.168.1.20", mac="02:00:00:00:00:20", **kwargs):
    return DiscoveredHost(ip=ip, mac=mac, source="active", state="REACHABLE", **kwargs)


def test_events_publish_only_committed_records_and_ignore_rolled_back_flushes(db):
    received = []
    db.events.subscribe(received.append)
    with pytest.raises(RuntimeError):
        with db.session() as session:
            session.add(Event(event_type="device_online", description="rolled back"))
            session.flush()
            raise RuntimeError("failure after flush")
    assert received == []
    item = EventManager(db).record("device_online", "committed")
    assert [(event.id, event.description) for event in received] == [(item.id, "committed")]
    assert EventManager(db).list_events()[0].id == item.id


def test_queued_events_do_not_call_unsubscribed_consumers(db):
    queued, received = [], []
    unsubscribe = db.events.subscribe(received.append, dispatcher=queued.append)
    EventManager(db).record("device_online", "queued")
    unsubscribe()
    queued[0]()
    assert received == []


def test_event_consumer_failure_does_not_break_other_consumers_or_transaction(db):
    received = []
    db.events.subscribe(lambda _: (_ for _ in ()).throw(RuntimeError("view closed")))
    db.events.subscribe(received.append)
    EventManager(db).record("device_online", "durable")
    assert len(received) == 1 and len(EventManager(db).list_events()) == 1


def test_conflicting_mac_claims_stay_separate_and_are_not_enforcement_targets(db):
    manager = DeviceManager(db)
    observations = [host(), host(mac="02:00:00:00:00:21")]
    assert len(_merge_discovery(observations)) == 2
    manager.reconcile_discovery(observations)
    for device in manager.list_devices():
        ProfileManager(db).create_profile(device.name, "Blocked", "blocked")
        assert device.identity_conflict
        assert not PolicyEngine(db).evaluate_device(device.name).enforcement_eligible
    assert PolicyEngine(db).blocked_ips() == []
    assert sum(e.event_type == "identity_conflict" for e in EventManager(db).list_events()) == 2
    with pytest.raises(ValidationError):
        device = manager.list_devices()[0]
        IdentityManager(db).resolve_conflict(device.id, expected_ip=device.ip, expected_mac=device.mac, reason="review")


def test_multi_address_history_and_service_changes_survive_restart(db):
    manager = DeviceManager(db)
    observations = [host("fe80::20", interface="wlan0"), host(interface="eth0", scan_method="nmap", open_tcp_ports=(22,), services=("ssh",))]
    manager.reconcile_discovery(observations)
    device = manager.list_devices()[0]
    assert device.ip == "192.168.1.20"
    manager.reconcile_discovery([host(scan_method="nmap", open_tcp_ports=(443,), services=("https",))])
    with db.session() as session:
        assert len(list(session.scalars(select(AddressEvidence)))) == 3
        assert len(list(session.scalars(select(ServiceEvidence)))) == 2
    restarted = DiscoveryService(device_manager=DeviceManager(db))
    identity = restarted.resolver.get(device.mac)
    assert identity.current_ip == device.ip
    assert identity.ips == {"192.168.1.20", "fe80::20"}
    assert identity.interfaces == {"wlan0", "eth0"}


def test_identity_merge_requires_review_and_refuses_policy_transfer(db):
    manager = DeviceManager(db)
    old = manager.add_device("Old", "00:00:00:00:00:20")
    new = manager.add_device("Randomized", "02:00:00:00:00:20")
    identity = IdentityManager(db)
    options = dict(expected_macs=(old.mac, new.mac), reason="Physical device verified")
    with pytest.raises(ValidationError):
        identity.merge(old.id, new.id, **options)
    ProfileManager(db).create_profile(new.name, "Child", "controlled")
    with pytest.raises(ValidationError, match="policies"):
        identity.merge(old.id, new.id, confirmed=True, **options)
    assert len(manager.list_devices()) == 2


def test_reviewed_mac_rotation_keeps_device_id_then_split_does_not_clone_policy(db):
    manager = DeviceManager(db)
    old = manager.add_device("Old", "00:00:00:00:00:20")
    new = manager.add_device("Randomized", "02:00:00:00:00:20")
    identity = IdentityManager(db)
    identity.merge(old.id, new.id, expected_macs=(old.mac, new.mac), reason="Physical device verified", confirmed=True)
    manager.reconcile_discovery([host()])
    assert len(manager.list_devices()) == 1
    assert manager.get_device_by_mac(new.mac).id == old.id
    assert manager.get_device_by_mac(old.mac).online
    split = identity.split(old.id, new.mac, name="Separate device", confirmed=True)
    assert split.id != old.id and not split.online
    assert ProfileManager(db).list_profiles(device_name=split.name) == []
    assert manager.get_device_by_mac(old.mac).identity_conflict


def test_cancelled_discovery_preserves_database_and_runtime_state(db, monkeypatch):
    manager = DeviceManager(db)
    manager.reconcile_discovery([host()])
    service = DiscoveryService(device_manager=manager)
    original = manager.list_devices()[0]
    def scan(*_args, token, **_kwargs):
        token.cancel()
        return DiscoveryReport((host("192.168.1.99"),))
    monkeypatch.setattr("network.discovery_service.scan_network_report", scan)
    snapshot = service.scan()
    assert snapshot.cancelled and not snapshot.complete and snapshot.error is None
    assert manager.list_devices()[0].ip == original.ip
    assert manager.list_devices()[0].last_seen == original.last_seen
    assert service.resolver.get(original.mac).current_ip == original.ip
    assert not service.running
    with db.session() as session:
        assert session.scalar(select(ScanRecord)).cancelled


def test_cancelled_child_is_reaped_promptly(tmp_path):
    token = CancellationToken()
    pid_file = tmp_path / "started"
    failures = []
    def work():
        try:
            run_process([sys.executable, "-c", "import pathlib,sys,time; pathlib.Path(sys.argv[1]).write_text('ready'); time.sleep(60)", str(pid_file)],
                        token=token, timeout=90, capture_output=True, text=True)
        except CancelledError:
            failures.append("cancelled")
    worker = threading.Thread(target=work)
    worker.start()
    deadline = time.monotonic() + 5
    while not pid_file.exists() and time.monotonic() < deadline:
        time.sleep(.01)
    assert pid_file.exists()
    token.cancel()
    worker.join(timeout=3)
    assert not worker.is_alive() and failures == ["cancelled"]


def test_child_timeout_and_nonzero_exit_are_preserved():
    with pytest.raises(subprocess.TimeoutExpired):
        run_process([sys.executable, "-c", "import time; time.sleep(10)"], token=CancellationToken(), timeout=.1)
    with pytest.raises(subprocess.CalledProcessError):
        run_process([sys.executable, "-c", "raise SystemExit(7)"], token=CancellationToken(), check=True)


def test_dhcp_names_require_matching_address_mac_and_unexpired_lease(tmp_path):
    path = tmp_path / "leases"
    path.write_text("0 02:00:00:00:00:20 192.168.1.20 tablet *\n1 02:00:00:00:00:21 192.168.1.21 expired *\n")
    observed = host()
    enrich_leases([observed], (str(path),))
    assert observed.hostname == "tablet" and "dhcp" in observed.source
    assert parse_leases(path.read_text(), now=2) == {("192.168.1.20", observed.mac): "tablet"}
    mismatch = host(mac="02:00:00:00:00:99")
    enrich_leases([mismatch], (str(path),))
    assert mismatch.hostname is None
