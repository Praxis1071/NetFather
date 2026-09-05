from __future__ import annotations
import datetime as dt
from pathlib import Path
import pytest

from core.config import Config, GeneralConfig, DiscoveryConfig, save_config, load_config
from core.database import Database
from core.time_utils import utc_now
from firewall.backends import NftablesBackend, WindowsFirewallBackend, PfBackend, get_firewall_backend
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
    assert len(hosts) == 1
    assert hosts[0].hostname == "phone"
    assert hosts[0].source == "active+passive"

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
        device = DeviceManager._find_by_mac(session, host.mac)
        device.last_seen = utc_now() - dt.timedelta(seconds=20)
    new, updated, offline = DeviceManager(db).reconcile_discovery([], auto_register=True, offline_after_seconds=10)
    assert offline == 1
    assert DeviceManager(db).get_device_by_mac(host.mac).online is False

def test_policy_engine_profile_block_precedes_default_allow(db):
    DeviceManager(db).add_device("Kid Tablet", "AA:BB:CC:DD:EE:31", ip="192.168.1.31")
    ProfileManager(db).create_profile("Kid Tablet", "Child", "blocked")
    policy = PolicyEngine(db).evaluate_device("Kid Tablet")
    assert policy.allowed is False
    assert policy.reason.startswith("profile:")
    assert PolicyEngine(db).blocked_ips() == ["192.168.1.31"]

def test_firewall_previews_are_scoped_and_local_only():
    nft = NftablesBackend().preview(["192.168.1.31"])
    assert "table inet netfather" in nft and "192.168.1.31" in nft
    win = WindowsFirewallBackend().preview(["10.0.0.8"])
    assert "-Group 'NetFather'" in win and "10.0.0.8" in win
    pf = PfBackend().preview(["172.16.0.4"])
    assert "block drop quick" in pf
    with pytest.raises(ValueError):
        NftablesBackend().preview(["8.8.8.8"])

def test_auto_firewall_backend_selection():
    assert get_firewall_backend("auto", "linux").name == "nftables"
    assert get_firewall_backend("auto", "win32").name == "windows"
    assert get_firewall_backend("auto", "darwin").name == "pf"

def test_config_save_round_trip(tmp_path: Path):
    path = tmp_path / "config.toml"
    cfg = Config(general=GeneralConfig(data_dir=str(tmp_path / "data")),
                 discovery=DiscoveryConfig(mode="active", interval_seconds=20, offline_after_seconds=60),
                 config_path=path)
    save_config(cfg)
    loaded = load_config(path)
    assert loaded.discovery.mode == "active"
    assert loaded.discovery.interval_seconds == 20
    assert loaded.general.data_dir == str(tmp_path / "data")

def test_topology_contains_router_and_policy_state(db, monkeypatch):
    DeviceManager(db).add_device("Laptop", "AA:BB:CC:DD:EE:41", ip="192.168.1.41")
    monkeypatch.setattr("network.topology.get_network_status", lambda: NetworkStatus(interface="eth0", local_ip="192.168.1.2", gateway="192.168.1.1"))
    topology = build_topology(db)
    assert any(n.kind == "router" for n in topology.nodes)
    assert any(n.label == "Laptop" for n in topology.nodes)
    assert len(topology.edges) == 1

def test_old_sqlite_schema_is_migrated_additively(tmp_path: Path):
    import sqlite3
    path = tmp_path / "legacy.db"
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE devices (id INTEGER PRIMARY KEY, name VARCHAR(128) UNIQUE NOT NULL, mac VARCHAR(17) UNIQUE NOT NULL, ip VARCHAR(45), vendor VARCHAR(128), device_type VARCHAR(32), created_at DATETIME, last_seen DATETIME)")
    con.execute("CREATE TABLE events (id INTEGER PRIMARY KEY, timestamp DATETIME, event_type VARCHAR(32) NOT NULL, description VARCHAR(512) NOT NULL)")
    con.commit(); con.close()
    migrated = Database(path); migrated.init_db()
    with migrated.engine.connect() as connection:
        device_cols = {row[1] for row in connection.exec_driver_sql("PRAGMA table_info(devices)")}
        event_cols = {row[1] for row in connection.exec_driver_sql("PRAGMA table_info(events)")}
    migrated.close()
    assert {"hostname", "os_hint", "online", "auto_registered"} <= device_cols
    assert {"device_mac", "severity", "metadata_json"} <= event_cols


def test_rule_and_profile_changes_generate_audit_events(db):
    from manager.rule_manager import RuleManager
    DeviceManager(db).add_device("Phone", "AA:BB:CC:DD:EE:51", ip="192.168.1.51")
    profile = ProfileManager(db).create_profile("Phone", "Child", "controlled")
    rule = RuleManager(db).create_rule("Phone", "block", "22:00-07:00")
    RuleManager(db).set_enabled(rule.id, False)
    ProfileManager(db).set_mode(profile.id, "blocked")
    kinds = {event.event_type for event in EventManager(db).list_events(limit=20)}
    assert {"profile_created", "profile_changed", "rule_created", "rule_changed"} <= kinds


def test_monitor_snapshot_contains_policy_counts(db, monkeypatch):
    from monitor.monitor import Monitor
    DeviceManager(db).add_device("Allowed", "AA:BB:CC:DD:EE:61", ip="192.168.1.61")
    DeviceManager(db).add_device("Blocked", "AA:BB:CC:DD:EE:62", ip="192.168.1.62")
    ProfileManager(db).create_profile("Blocked", "Guest", "blocked")
    monkeypatch.setattr("monitor.monitor.get_network_status", lambda: NetworkStatus(interface=None))
    snap = Monitor(db).snapshot()
    assert snap.allowed_devices == 1
    assert snap.blocked_devices == 1


def test_service_plans_cover_supported_platforms():
    from core.service import service_plan
    assert "systemd" in (service_plan("linux").destination or "") or "systemd" in service_plan("linux").description.lower()
    assert "schtasks" in service_plan("win32").description.lower()
    assert "LaunchDaemons" in (service_plan("darwin").destination or "")
