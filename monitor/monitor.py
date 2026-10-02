"""Cross-platform network telemetry and optional policy-aware packet sampling."""
from __future__ import annotations
import time
from dataclasses import dataclass
from core.database import Database
from manager.policy_engine import PolicyEngine
from network.interface import get_network_status

@dataclass(frozen=True)
class TrafficSnapshot:
    interface: str | None
    bytes_sent: int
    bytes_recv: int
    packets_sent: int
    packets_recv: int
    errors_in: int
    errors_out: int
    drops_in: int
    drops_out: int
    timestamp: float
    allowed_devices: int = 0
    blocked_devices: int = 0

@dataclass(frozen=True)
class PolicyTrafficSnapshot:
    duration_seconds: float
    allowed_packets: int
    allowed_bytes: int
    blocked_packets: int
    blocked_bytes: int
    unknown_packets: int
    unknown_bytes: int
    detail: str = ""

class Monitor:
    def __init__(self, db: Database) -> None:
        self.db = db
    def snapshot(self) -> TrafficSnapshot:
        interface = get_network_status().interface
        policies = PolicyEngine(self.db).evaluate_all()
        allowed = sum(1 for p in policies if p.allowed); blocked = sum(1 for p in policies if not p.allowed)
        try:
            import psutil
            pernic = psutil.net_io_counters(pernic=True)
            counters = pernic.get(interface) if interface else None
            if counters is None: counters = psutil.net_io_counters()
            return TrafficSnapshot(interface, int(counters.bytes_sent), int(counters.bytes_recv),
                int(counters.packets_sent), int(counters.packets_recv), int(counters.errin), int(counters.errout),
                int(counters.dropin), int(counters.dropout), time.time(), allowed, blocked)
        except Exception:
            return TrafficSnapshot(interface, 0, 0, 0, 0, 0, 0, 0, 0, time.time(), allowed, blocked)

    def capture_policy_traffic(self, duration_seconds: float = 1.0, interface: str | None = None) -> PolicyTrafficSnapshot:
        """Sample real packets and classify them by the current effective policy.

        Scapy/Npcap/root privileges may be required. This is observation only;
        packet capture never changes firewall state.
        """
        duration = max(0.1, min(float(duration_seconds), 30.0))
        policies = PolicyEngine(self.db).evaluate_all()
        by_ip = {p.ip: p.allowed for p in policies if p.ip}
        counters = {"allowed_packets":0,"allowed_bytes":0,"blocked_packets":0,"blocked_bytes":0,"unknown_packets":0,"unknown_bytes":0}
        try:
            from scapy.all import IP, sniff  # type: ignore[import-not-found]
        except ImportError:
            return PolicyTrafficSnapshot(duration, 0,0,0,0,0,0,"Scapy unavailable")
        def account(packet) -> None:
            if not packet.haslayer(IP): return
            src, dst = str(packet[IP].src), str(packet[IP].dst); length = len(packet)
            decision = by_ip.get(src)
            if decision is None: decision = by_ip.get(dst)
            prefix = "unknown" if decision is None else ("allowed" if decision else "blocked")
            counters[f"{prefix}_packets"] += 1; counters[f"{prefix}_bytes"] += length
        try:
            sniff(iface=interface or get_network_status().interface, timeout=duration, store=False, prn=account)
        except Exception as exc:
            return PolicyTrafficSnapshot(duration, 0,0,0,0,0,0,f"capture unavailable: {exc}")
        return PolicyTrafficSnapshot(duration, counters["allowed_packets"], counters["allowed_bytes"],
            counters["blocked_packets"], counters["blocked_bytes"], counters["unknown_packets"], counters["unknown_bytes"], "captured")
