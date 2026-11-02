"""Live logical topology derived from network status and persisted devices."""
from __future__ import annotations
from dataclasses import dataclass, field
import json
import shutil
from sqlalchemy import select
from models.network_evidence import AddressEvidence
from core.operations import run_process
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
    evidence: str = "unknown"

@dataclass(frozen=True)
class TopologyEdge:
    source: str
    target: str
    status: str = "up"
    evidence: str = "unknown"
    detail: str = ""

@dataclass
class NetworkTopology:
    nodes: list[TopologyNode] = field(default_factory=list)
    edges: list[TopologyEdge] = field(default_factory=list)
    warnings: tuple[str, ...] = ()


def _link_evidence():
    binary = shutil.which("ip")
    if not binary:
        return [], ("Interface topology unavailable: iproute2 missing.",)
    try:
        result = run_process([binary, "-j", "-d", "link", "show"], capture_output=True, text=True, timeout=3, check=True)
        data = json.loads(result.stdout)
        if not isinstance(data, list):
            raise ValueError("Unexpected link inventory")
        return data, ()
    except Exception as exc:
        return [], (f"Interface topology unavailable: {exc}",)


def build_topology(db: Database) -> NetworkTopology:
    status = get_network_status()
    links, warnings = _link_evidence()
    topology = NetworkTopology(warnings=warnings)
    topology.nodes.append(TopologyNode("router", "Router/Gateway", "router", status.gateway,
        bool(status.gateway), True, status.interface or "unknown interface", "observed" if status.gateway else "unknown"))
    names = {item.get("ifindex"): item.get("ifname") for item in links}
    known = set()
    for link in links:
        name = link.get("ifname")
        if not name or name == "lo":
            continue
        known.add(name)
        kind = link.get("linkinfo", {}).get("info_kind", "interface")
        detail = f"{kind}; {link.get('operstate', 'UNKNOWN')}"
        if kind == "vlan":
            detail += f"; VLAN {link.get('linkinfo', {}).get('info_data', {}).get('id', 'unknown')}"
        topology.nodes.append(TopologyNode(f"interface:{name}", name, kind, online=link.get("operstate") == "UP", detail=detail, evidence="observed"))
        master = link.get("master")
        master = names.get(master, master)
        if master:
            topology.edges.append(TopologyEdge(f"interface:{master}", f"interface:{name}", evidence="observed", detail="bridge/master port"))
        parent = names.get(link.get("link_index"))
        if parent and kind == "vlan":
            topology.edges.append(TopologyEdge(f"interface:{parent}", f"interface:{name}", evidence="observed", detail="VLAN parent"))
    policies = {p.mac: p for p in PolicyEngine(db).evaluate_all()}
    with db.session() as session:
        paths = list(session.scalars(select(AddressEvidence)))
        by_device = {}
        for path in paths:
            by_device.setdefault(path.device_id, []).append(path)
    devices = DeviceManager(db).list_devices()
    for device in devices:
        policy = policies.get(device.mac)
        key = f"device:{device.mac}"
        detail = policy.reason if policy else "default-allow"
        if device.identity_conflict:
            detail += "; identity conflict; enforcement excluded"
        topology.nodes.append(TopologyNode(key, device.name, device.device_type or "device", device.ip,
            bool(device.online), policy.allowed if policy else True, detail, "observed"))
        interfaces = {path.interface for path in by_device.get(device.id, []) if path.interface in known}
        for interface in sorted(interfaces):
            topology.edges.append(TopologyEdge(f"interface:{interface}", key, "up" if device.online else "down",
                "observed", "historical neighbor observation; not proof of current reachability"))
        if not interfaces:
            topology.edges.append(TopologyEdge("router", key, "up" if device.online else "down", "unknown", "device attachment unknown"))
    if status.interface in known:
        topology.edges.append(TopologyEdge("router", f"interface:{status.interface}", evidence="inferred", detail="host default route; remote transit path unverified"))
    # AP client relationships are exposed only when the kernel wireless source
    # actually reports the station on that local interface.
    iw = shutil.which("iw")
    if iw:
        for interface in sorted(known):
            try:
                result = run_process([iw, "dev", interface, "station", "dump"], capture_output=True, text=True, timeout=2, check=False)
            except Exception:
                continue
            if result.returncode:
                continue
            try:
                info = run_process([iw, "dev", interface, "info"], capture_output=True, text=True, timeout=2, check=False)
                is_ap = info.returncode == 0 and any(line.strip() == "type AP" for line in info.stdout.splitlines())
            except Exception:
                is_ap = False
            stations = {line.split()[1].upper() for line in result.stdout.splitlines() if line.startswith("Station ") and len(line.split()) > 1}
            for device in devices:
                if device.mac in stations:
                    topology.edges.append(TopologyEdge(f"interface:{interface}", f"device:{device.mac}", evidence="observed",
                        detail="AP client observed by kernel" if is_ap else "wireless peer observed; AP/client role unknown"))
    return topology
