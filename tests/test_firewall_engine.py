from pathlib import Path
from types import SimpleNamespace

from core.config import Config, FirewallConfig
from core.database import Database
from firewall.base import FirewallResult
from firewall.engine import FirewallEngine
from manager.device_manager import DeviceManager
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

    engine = FirewallEngine(
        db,
        Config(firewall=FirewallConfig(backend="none", enforcement_enabled=True)),
    )
    backend = CaptureBackend()
    engine.backend = backend

    result = engine.sync(apply=True)

    assert result.blocked_ips == ("192.168.1.21",)
    assert backend.calls == [(["192.168.1.21"], True)]
    db.close()
