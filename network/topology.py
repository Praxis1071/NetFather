"""Live logical topology derived from network status and persisted devices."""
from __future__ import annotations
from dataclasses import dataclass, field
from core.database import Database
from manager.device_manager import DeviceManager
from manager.policy_engine import PolicyEngine
from network.interface import get_network_status

@dataclass(frozen=True)
class TopologyNode:
    key: str
    label: str
    kind: str
    ip: str | None = None
    online: bool = True
    allowed: bool = True
    detail: str = ""

@dataclass(frozen=True)
class TopologyEdge:
    source: str
    target: str
    status: str = "up"

@dataclass
class NetworkTopology:
    nodes: list[TopologyNode] = field(default_factory=list)
    edges: list[TopologyEdge] = field(default_factory=list)


def build_topology(db: Database) -> NetworkTopology:
    status = get_network_status()
    topology = NetworkTopology()
    router_key = "router"
    topology.nodes.append(TopologyNode(router_key, "Router/Gateway", "router", status.gateway, True, True,
                                       status.interface or "unknown interface"))
    policies = {p.mac: p for p in PolicyEngine(db).evaluate_all()}
    for device in DeviceManager(db).list_devices():
        policy = policies.get(device.mac)
        key = f"device:{device.mac}"
        topology.nodes.append(TopologyNode(key, device.name, device.device_type or "device", device.ip,
                                           bool(device.online), policy.allowed if policy else True,
                                           policy.reason if policy else "default-allow"))
        topology.edges.append(TopologyEdge(router_key, key, "up" if device.online else "down"))
    return topology
