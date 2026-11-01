from core.database import Database
from manager.device_manager import DeviceManager
from network.discovery import DiscoveredHost
from network.interface import NetworkStatus
from network.topology import build_topology


def test_topology_distinguishes_observation_inference_and_unknown(tmp_path, monkeypatch):
    db = Database(tmp_path / "topology.db")
    db.init_db()
    manager = DeviceManager(db)
    manager.reconcile_discovery([DiscoveredHost("192.168.1.20", interface="eth0", mac="02:00:00:00:00:20", source="active")])
    manager.add_device("Unknown attachment", "02:00:00:00:00:21")
    monkeypatch.setattr("network.topology.get_network_status", lambda: NetworkStatus(interface="br0", gateway="192.168.1.1"))
    monkeypatch.setattr("network.topology._link_evidence", lambda: ([
        {"ifname": "br0", "ifindex": 1, "operstate": "UP", "linkinfo": {"info_kind": "bridge"}},
        {"ifname": "eth0", "ifindex": 2, "master": "br0", "operstate": "UP"},
        {"ifname": "eth0.20", "ifindex": 3, "link_index": 2, "linkinfo": {"info_kind": "vlan", "info_data": {"id": 20}}},
    ], ()))
    monkeypatch.setattr("network.topology.shutil.which", lambda _: None)
    topology = build_topology(db)
    assert any(e.detail == "bridge/master port" and e.evidence == "observed" for e in topology.edges)
    assert any(e.detail == "VLAN parent" and e.evidence == "observed" for e in topology.edges)
    assert any(e.target == "device:02:00:00:00:00:20" and e.evidence == "observed" for e in topology.edges)
    assert any(e.target == "device:02:00:00:00:00:21" and e.evidence == "unknown" for e in topology.edges)
    assert any(e.source == "router" and e.target == "interface:br0" and e.evidence == "inferred" for e in topology.edges)
    db.close()


def test_wireless_client_role_requires_observed_ap_mode(tmp_path, monkeypatch):
    from types import SimpleNamespace
    db = Database(tmp_path / "wireless.db"); db.init_db()
    DeviceManager(db).reconcile_discovery([DiscoveredHost("192.168.1.20", interface="wlan0", mac="02:00:00:00:00:20", source="active")])
    monkeypatch.setattr("network.topology.get_network_status", lambda: NetworkStatus())
    monkeypatch.setattr("network.topology._link_evidence", lambda: ([{"ifname": "wlan0", "ifindex": 2, "operstate": "UP"}], ()))
    monkeypatch.setattr("network.topology.shutil.which", lambda name: "/usr/sbin/iw" if name == "iw" else None)
    mode = ["AP"]
    def run(args, **kwargs):
        output = f"Interface wlan0\n\ttype {mode[0]}\n" if args[-1] == "info" else "Station 02:00:00:00:00:20 (on wlan0)\n"
        return SimpleNamespace(returncode=0, stdout=output)
    monkeypatch.setattr("network.topology.run_process", run)
    assert any(edge.detail == "AP client observed by kernel" for edge in build_topology(db).edges)
    mode[0] = "managed"
    edges = build_topology(db).edges
    assert not any(edge.detail == "AP client observed by kernel" for edge in edges)
    assert any("AP/client role unknown" in edge.detail for edge in edges)
    db.close()
