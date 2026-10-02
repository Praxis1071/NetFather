from __future__ import annotations
import datetime as dt
import sqlite3
from pathlib import Path

import pytest

from core.config import Config, GeneralConfig, DiscoveryConfig, save_config, load_config
from core.database import Database
from core.time_utils import utc_now
from firewall.backends import NftablesBackend, get_firewall_backend
from manager.device_manager import DeviceManager
from manager.event_manager import EventManager
from manager.policy_engine import PolicyEngine
from manager.profile_manager import ProfileManager
from network.discovery import DiscoveredHost, _merge_discovery
from network.interface import NetworkStatus
from network.topology import build_topology

@pytest.fixture
def db(tmp_path: Path):
    database = Database(tmp_path / "nf.db"); database.init_db(); yield database; database.close()

def test_hybrid_discovery_merge_preserves_richer_fields():
    passive = DiscoveredHost("192.168.1.5", "eth0", "aa:bb:cc:dd:ee:ff", "STALE", source="passive")
    active = DiscoveredHost("192.168.1.5", None, "aa:bb:cc:dd:ee:ff", "REACHABLE", hostname="phone", source="active")
    hosts = _merge_discovery([passive, active])
    assert len(hosts) == 1 and hosts[0].hostname == "phone" and hosts[0].source == "active+passive"

def test_reconcile_auto_registers_and_audits(db):
    host = DiscoveredHost("192.168.1.20", mac="aa:bb:cc:dd:ee:20", hostname="tablet", device_type="tablet")
    new, updated, offline = DeviceManager(db).reconcile_discovery([host], auto_register=True, offline_after_seconds=30)
    assert (new, updated, offline) == (1, 0, 0)
    device = DeviceManager(db).get_device_by_mac(host.mac)
    assert device and device.online and device.auto_registered and device.hostname == "tablet"
    assert EventManager(db).list_events(limit=10)[0].event_type == "device_discovered"

def test_reconcile_marks_stale_device_offline(db):
    host = DiscoveredHost("192.168.1.21", mac="aa:bb:cc:dd:ee:21")
    DeviceManager(db).reconcile_discovery([host], auto_register=True, offline_after_seconds=10)
    with db.session() as session:
        device = DeviceManager._find_by_mac(session, host.mac); device.last_seen = utc_now() - dt.timedelta(seconds=20)
    _, _, offline = DeviceManager(db).reconcile_discovery([], auto_register=True, offline_after_seconds=10)
    assert offline == 1 and DeviceManager(db).get_device_by_mac(host.mac).online is False

def test_policy_engine_profile_block_precedes_default_allow(db):
    DeviceManager(db).add_device("Kid Tablet", "AA:BB:CC:DD:EE:31", ip="192.168.1.31")
    ProfileManager(db).create_profile("Kid Tablet", "Child", "blocked")
    policy = PolicyEngine(db).evaluate_device("Kid Tablet")
    assert policy.allowed is False and policy.reason.startswith("profile:")
    assert PolicyEngine(db).blocked_ips() == ["192.168.1.31"]

def test_linux_firewall_preview_is_scoped_and_local_only():
    nft = NftablesBackend().preview(["192.168.1.31"])
    assert "table inet netfather" in nft and "192.168.1.31" in nft
    with pytest.raises(ValueError):
        NftablesBackend().preview(["8.8.8.8"])

def test_linux_firewall_backend_selection():
    assert get_firewall_backend("auto").name == "nftables"
    assert get_firewall_backend("none").name == "none"
    with pytest.raises(ValueError):
        get_firewall_backend("windows")

def test_config_save_round_trip(tmp_path: Path):
    path = tmp_path / "config.toml"
    cfg = Config(general=GeneralConfig(data_dir=str(tmp_path / "data")), discovery=DiscoveryConfig(mode="active", interval_seconds=20, offline_after_seconds=60), config_path=path)
    save_config(cfg); loaded = load_config(path)
    assert loaded.discovery.mode == "active" and loaded.discovery.interval_seconds == 20 and loaded.general.data_dir == str(tmp_path / "data")

def test_topology_contains_router_and_policy_state(db, monkeypatch):
    DeviceManager(db).add_device("Laptop", "AA:BB:CC:DD:EE:41", ip="192.168.1.41")
    monkeypatch.setattr("network.topology.get_network_status", lambda: NetworkStatus(interface="eth0", local_ip="192.168.1.2", gateway="192.168.1.1"))
    topology = build_topology(db)
    assert any(n.kind == "router" for n in topology.nodes) and any(n.label == "Laptop" for n in topology.nodes) and len(topology.edges) == 1

def test_old_sqlite_schema_is_migrated_additively(tmp_path: Path):
    path = tmp_path / "legacy.db"
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE devices (id INTEGER PRIMARY KEY, name VARCHAR(128) UNIQUE NOT NULL, mac VARCHAR(17) UNIQUE NOT NULL, ip VARCHAR(45), vendor VARCHAR(128), device_type VARCHAR(32), created_at DATETIME, last_seen DATETIME)")
    con.execute("CREATE TABLE events (id INTEGER PRIMARY KEY, timestamp DATETIME, event_type VARCHAR(32) NOT NULL, description VARCHAR(512) NOT NULL)")
    con.commit(); con.close()
    migrated = Database(path); migrated.init_db()
    with migrated.engine.connect() as connection:
        device_cols = {row[1] for row in connection.exec_driver_sql("PRAGMA table_info(devices)")}; event_cols = {row[1] for row in connection.exec_driver_sql("PRAGMA table_info(events)")}
    migrated.close()
    assert {"hostname", "os_hint", "online", "auto_registered"} <= device_cols and {"device_mac", "severity", "metadata_json"} <= event_cols

def test_rule_and_profile_changes_generate_audit_events(db):
    from manager.rule_manager import RuleManager
    DeviceManager(db).add_device("Phone", "AA:BB:CC:DD:EE:51", ip="192.168.1.51")
    profile = ProfileManager(db).create_profile("Phone", "Child", "controlled")
    rule = RuleManager(db).create_rule("Phone", "block", "22:00-07:00")
    RuleManager(db).set_enabled(rule.id, False); ProfileManager(db).set_mode(profile.id, "blocked")
    kinds = {event.event_type for event in EventManager(db).list_events(limit=20)}
    assert {"profile_created", "profile_changed", "rule_created", "rule_changed"} <= kinds

def test_monitor_snapshot_contains_policy_counts(db, monkeypatch):
    from monitor.monitor import Monitor
    DeviceManager(db).add_device("Allowed", "AA:BB:CC:DD:EE:61", ip="192.168.1.61")
    DeviceManager(db).add_device("Blocked", "AA:BB:CC:DD:EE:62", ip="192.168.1.62")
    ProfileManager(db).create_profile("Blocked", "Guest", "blocked")
    monkeypatch.setattr("monitor.monitor.get_network_status", lambda: NetworkStatus(interface=None))
    snap = Monitor(db).snapshot(); assert snap.allowed_devices == 1 and snap.blocked_devices == 1

def test_linux_service_plan_uses_systemd():
    from core.service import service_plan
    plan = service_plan()
    assert plan.family == "linux" and "systemd" in (plan.destination or "") and "scheduler.scheduler" in plan.command
