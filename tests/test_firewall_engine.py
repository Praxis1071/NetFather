from pathlib import Path
import json
from types import SimpleNamespace

import pytest

from core.config import Config, FirewallConfig
from core.exceptions import ConfigError
from core.database import Database
from firewall.base import FirewallResult
from firewall.engine import FirewallEngine
from manager.device_manager import DeviceManager
from manager.event_manager import EventManager
from manager.profile_manager import ProfileManager


class CaptureBackend:
    name = "capture"

    def __init__(self) -> None:
        self.calls = []

    def apply(self, blocked_ips, *, apply=False):
        self.calls.append((list(blocked_ips), apply))
        return FirewallResult(self.name, apply, tuple(blocked_ips), "captured")

    def rollback(self, *, apply=False):
        return FirewallResult(self.name, apply, (), "rollback")


def test_firewall_sync_never_blocks_local_or_gateway_ip(tmp_path: Path, monkeypatch) -> None:
    db = Database(tmp_path / "firewall.db")
    db.init_db()
    devices = DeviceManager(db)
    devices.add_device("Self", "02:00:00:00:00:01", ip="192.168.1.10")
    devices.add_device("Gateway", "02:00:00:00:00:02", ip="192.168.1.1")
    devices.add_device("Tablet", "02:00:00:00:00:03", ip="192.168.1.21")
    devices.add_device("Admin LAN", "02:00:00:00:00:04", ip="10.0.0.5")
    profiles = ProfileManager(db)
    profiles.create_profile("Self", "blocked", internet_mode="blocked")
    profiles.create_profile("Gateway", "blocked", internet_mode="blocked")
    profiles.create_profile("Tablet", "blocked", internet_mode="blocked")
    profiles.create_profile("Admin LAN", "blocked", internet_mode="blocked")

    monkeypatch.setattr(
        "firewall.engine.get_local_ipv4_addresses",
        lambda: {"192.168.1.10", "10.0.0.5"},
    )
    monkeypatch.setattr(
        "firewall.engine.get_network_status",
        lambda: SimpleNamespace(local_ip="192.168.1.10", gateway="192.168.1.1"),
    )
    monkeypatch.setattr("firewall.engine.get_local_ipv6_addresses", lambda: set())

    engine = FirewallEngine(
        db,
        Config(firewall=FirewallConfig(backend="none", enforcement_enabled=True, enforcement_topology="inline")),
    )
    backend = CaptureBackend()
    engine.backend = backend

    result = engine.sync(apply=True)

    assert result.blocked_ips == ("192.168.1.21",)
    assert backend.calls == [(["192.168.1.21"], True)]
    db.close()


def test_firewall_apply_rejects_unverified_enforcement_topology(tmp_path: Path) -> None:
    db = Database(tmp_path / "firewall-topology.db")
    db.init_db()
    engine = FirewallEngine(
        db,
        Config(firewall=FirewallConfig(backend="none", enforcement_enabled=True)),
    )
    try:
        with pytest.raises(ConfigError, match="enforcement_topology"):
            engine.sync(apply=True)
    finally:
        db.close()


def test_gateway_enforcement_requires_dual_stack_forwarding(tmp_path: Path, monkeypatch) -> None:
    db = Database(tmp_path / "firewall-gateway.db")
    db.init_db()
    engine = FirewallEngine(
        db,
        Config(
            firewall=FirewallConfig(
                backend="none",
                enforcement_enabled=True,
                enforcement_topology="gateway",
            )
        ),
    )
    monkeypatch.setattr(engine, "_ip_forwarding_enabled", lambda: False)
    try:
        with pytest.raises(ConfigError, match="IPv4"):
            engine.sync(apply=True)
    finally:
        db.close()


def test_firewall_sync_rejects_kernel_state_mismatch(tmp_path: Path, monkeypatch) -> None:
    db = Database(tmp_path / "firewall-reconcile.db")
    db.init_db()
    devices = DeviceManager(db)
    devices.add_device("Tablet", "02:00:00:00:00:03", ip="192.168.1.21")
    profiles = ProfileManager(db)
    profiles.create_profile("Tablet", "blocked", internet_mode="blocked")

    monkeypatch.setattr("firewall.engine.get_local_ipv4_addresses", lambda: set())
    monkeypatch.setattr("firewall.engine.get_local_ipv6_addresses", lambda: set())
    monkeypatch.setattr(
        "firewall.engine.get_network_status",
        lambda: SimpleNamespace(local_ip="192.168.1.10", gateway="192.168.1.1"),
    )

    class MismatchBackend(CaptureBackend):
        def read_blocked_ips(self):
            return ("192.168.1.22",)

    engine = FirewallEngine(
        db,
        Config(firewall=FirewallConfig(backend="none", enforcement_enabled=True, enforcement_topology="inline")),
    )
    backend = MismatchBackend()
    engine.backend = backend

    try:
        with pytest.raises(RuntimeError, match="kernel state desired policy"):
            engine.sync(apply=True)
    finally:
        db.close()


def test_firewall_detect_drift_is_observation_only(tmp_path: Path, monkeypatch) -> None:
    db = Database(tmp_path / "firewall-drift.db")
    db.init_db()
    devices = DeviceManager(db)
    devices.add_device("Tablet", "02:00:00:00:00:03", ip="192.168.1.21")
    profiles = ProfileManager(db)
    profiles.create_profile("Tablet", "blocked", internet_mode="blocked")

    monkeypatch.setattr("firewall.engine.get_local_ipv4_addresses", lambda: set())
    monkeypatch.setattr("firewall.engine.get_local_ipv6_addresses", lambda: set())
    monkeypatch.setattr(
        "firewall.engine.get_network_status",
        lambda: SimpleNamespace(local_ip="192.168.1.10", gateway="192.168.1.1"),
    )

    class DriftBackend(CaptureBackend):
        def read_blocked_ips(self):
            return ()

    engine = FirewallEngine(
        db,
        Config(firewall=FirewallConfig(backend="none", enforcement_enabled=True, enforcement_topology="inline")),
    )
    backend = DriftBackend()
    engine.backend = backend

    try:
        assert engine.detect_drift() is True
        assert backend.calls == []
        events = EventManager(db).list_events(event_type="firewall_drift")
        assert len(events) == 1
        assert events[0].severity == "error"
        metadata = json.loads(events[0].metadata_json or "{}")
        assert metadata["expected"] == ["192.168.1.21"]
        assert metadata["actual"] == []
    finally:
        db.close()


def test_firewall_detect_drift_returns_false_when_state_matches(tmp_path: Path, monkeypatch) -> None:
    db = Database(tmp_path / "firewall-no-drift.db")
    db.init_db()
    devices = DeviceManager(db)
    devices.add_device("Tablet", "02:00:00:00:00:03", ip="192.168.1.21")
    profiles = ProfileManager(db)
    profiles.create_profile("Tablet", "blocked", internet_mode="blocked")

    monkeypatch.setattr("firewall.engine.get_local_ipv4_addresses", lambda: set())
    monkeypatch.setattr("firewall.engine.get_local_ipv6_addresses", lambda: set())
    monkeypatch.setattr(
        "firewall.engine.get_network_status",
        lambda: SimpleNamespace(local_ip="192.168.1.10", gateway="192.168.1.1"),
    )

    class MatchingBackend(CaptureBackend):
        def read_blocked_ips(self):
            return ("192.168.1.21",)

    engine = FirewallEngine(
        db,
        Config(firewall=FirewallConfig(backend="none", enforcement_enabled=True, enforcement_topology="inline")),
    )
    engine.backend = MatchingBackend()

    try:
        assert engine.detect_drift() is False
        assert EventManager(db).list_events(event_type="firewall_drift") == []
    finally:
        db.close()


def test_firewall_detect_drift_treats_missing_firewall_state_as_drift(tmp_path: Path, monkeypatch) -> None:
    db = Database(tmp_path / "firewall-missing.db")
    db.init_db()
    devices = DeviceManager(db)
    devices.add_device("Tablet", "02:00:00:00:00:03", ip="192.168.1.21")
    profiles = ProfileManager(db)
    profiles.create_profile("Tablet", "blocked", internet_mode="blocked")

    monkeypatch.setattr("firewall.engine.get_local_ipv4_addresses", lambda: set())
    monkeypatch.setattr("firewall.engine.get_local_ipv6_addresses", lambda: set())
    monkeypatch.setattr(
        "firewall.engine.get_network_status",
        lambda: SimpleNamespace(local_ip="192.168.1.10", gateway="192.168.1.1"),
    )

    class MissingBackend(CaptureBackend):
        def read_blocked_ips(self):
            raise RuntimeError("nft table missing")

    engine = FirewallEngine(
        db,
        Config(firewall=FirewallConfig(backend="none", enforcement_enabled=True, enforcement_topology="inline")),
    )
    engine.backend = MissingBackend()

    try:
        assert engine.detect_drift() is True
        event = EventManager(db).list_events(event_type="firewall_drift")[0]
        metadata = json.loads(event.metadata_json or "{}")
        assert metadata["actual"] is None
        assert metadata["read_error"] == "nft table missing"
    finally:
        db.close()
