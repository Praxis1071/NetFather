"""Real IPv4/IPv6 neighbor notifications -> discovery -> durable presence."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

import pytest

pytestmark = pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux namespace test")


def test_kernel_neighbor_notifications_discovery_aging_and_restart(tmp_path):
    if os.geteuid() != 0 or not all(shutil.which(name) for name in ("ip", "ping")):
        pytest.skip("root + ip + ping required")
    suffix = uuid.uuid4().hex[:7]
    left, right, va, vb = (prefix + suffix for prefix in ("nfa", "nfb", "va", "vb"))
    def run(*args):
        return subprocess.run(args, check=True, capture_output=True, text=True, timeout=15)
    try:
        run("ip", "netns", "add", left)
        run("ip", "netns", "add", right)
        run("ip", "link", "add", va, "type", "veth", "peer", "name", vb)
        for ns, interface, v4, v6 in ((left, va, "10.204.0.1/24", "fd42:204::1/64"),
                                      (right, vb, "10.204.0.2/24", "fd42:204::2/64")):
            run("ip", "link", "set", interface, "netns", ns)
            run("ip", "-n", ns, "link", "set", "lo", "up")
            run("ip", "-n", ns, "link", "set", interface, "up")
            run("ip", "-n", ns, "addr", "add", v4, "dev", interface)
            run("ip", "-n", ns, "-6", "addr", "add", v6, "dev", interface, "nodad")
        run("ip", "netns", "exec", left, "ping", "-6", "-c", "1", "-W", "2", "fd42:204::2")
        script = r'''
import subprocess, sys, time
from sqlalchemy import select
from core.database import Database
from manager.device_manager import DeviceManager
from models.network_evidence import AddressEvidence
from network.discovery_service import DiscoveryService
from network.presence import PresenceMonitor
db = Database(sys.argv[1]); db.init_db()
events = []
monitor = PresenceMonitor(events.append); monitor.start()
deadline = time.monotonic() + 3
while monitor._process is None and time.monotonic() < deadline: time.sleep(.02)
assert monitor._process is not None, 'kernel monitor failed to start'
iface = sys.argv[2]
def entry(address, state):
    subprocess.run(['ip', 'neigh', 'replace', address, 'lladdr', '02:00:00:00:00:20', 'dev', iface, 'nud', state], check=True)
entry('10.204.0.20', 'reachable'); entry('fd42:204::20', 'reachable')
deadline = time.monotonic() + 3
while len([e for e in events if e.kind == 'added' and e.mac == '02:00:00:00:00:20']) < 2 and time.monotonic() < deadline: time.sleep(.02)
assert {e.address for e in events if e.kind == 'added'} >= {'10.204.0.20', 'fd42:204::20'}, events
service = DiscoveryService(device_manager=DeviceManager(db))
snapshot = service.scan(mode='passive', vendor_detection=False, offline_after_seconds=1)
assert snapshot.complete and not snapshot.error, snapshot
device = DeviceManager(db).get_device_by_mac('02:00:00:00:00:20')
assert device.online and device.ip == '10.204.0.20'
with db.session() as session:
    assert {p.ip for p in session.scalars(select(AddressEvidence).where(AddressEvidence.device_id == device.id))} == {'10.204.0.20', 'fd42:204::20'}
entry('10.204.0.20', 'stale'); entry('fd42:204::20', 'stale')
time.sleep(1.1)
snapshot = service.scan(mode='passive', vendor_detection=False, offline_after_seconds=1)
assert snapshot.complete and not DeviceManager(db).get_device_by_mac(device.mac).online
assert not service.resolver.get(device.mac).online
monitor.stop()
assert not monitor.running
db.close()
db = Database(sys.argv[1]); db.init_db()
restarted = DiscoveryService(device_manager=DeviceManager(db))
assert not restarted.resolver.get(device.mac).online
assert restarted.resolver.get(device.mac).ips >= {'10.204.0.20', 'fd42:204::20'}
db.close()
'''
        run("ip", "netns", "exec", left, sys.executable, "-c", script, str(tmp_path / "kernel.db"), va)
    finally:
        for ns in (left, right):
            subprocess.run(["ip", "netns", "del", ns], capture_output=True)
