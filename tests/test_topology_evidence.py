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
