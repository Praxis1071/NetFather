"""Execute discovery callbacks without requiring a graphical GTK session.

The production callback bodies are extracted, not reimplemented. This checks
state/feedback and the worker contract; GTK rendering still needs runtime QA.
"""
from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

from network.discovery_service import DiscoverySnapshot
from core.time_utils import utc_now
from core.i18n import tr


def page_callbacks():
    path = Path(__file__).resolve().parents[1] / "gui" / "discovery_page.py"
    source = ast.parse(path.read_text())
    cls = next(node for node in source.body if isinstance(node, ast.ClassDef))
    cls.bases = []
    cls.body = [node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name in {"_scan_finished", "_start_scan"}]
    namespace = {"DiscoverySnapshot": DiscoverySnapshot, "tr": tr}
    exec(compile(ast.Module(body=[cls], type_ignores=[]), str(path), "exec"), namespace)
    return namespace["DiscoveryPage"]()


def test_partial_scan_feedback_includes_warnings_and_previous_state_notice():
    page = page_callbacks()
    notifications = []
    timestamps = []
    page.state = SimpleNamespace(discovery=SimpleNamespace(), notify_changed=lambda: notifications.append(True))
    page._stop_pulse = lambda: None
    page.last_scan = SimpleNamespace(set_text=timestamps.append)
    snapshot = DiscoverySnapshot(utc_now(), utc_now(), scanned=1, warnings=("ARP requires privilege",), complete=False)
    page._scan_finished(snapshot)
    assert not page.state.discovery.running
    assert page.state.discovery.error is None
    assert "Partial scan" in page.state.discovery.status_message
    assert "previous state" in page.state.discovery.status_message
    assert "ARP requires privilege" in page.state.discovery.status_message
    assert notifications == [True]
    assert timestamps


def test_manual_scan_captures_reconciliation_config_before_worker_runs():
    page = page_callbacks()
    page.state = SimpleNamespace(discovery=SimpleNamespace(running=False), notify_changed=lambda: None)
    page.config = SimpleNamespace(discovery=SimpleNamespace(auto_register=False, offline_after_seconds=120, active_timeout_seconds=1))
    page.mode = SimpleNamespace(get_active_id=lambda: "hybrid")
    page.subnet = SimpleNamespace(get_text=lambda: "192.168.1.0/24")
    page.timeout = SimpleNamespace(get_value=lambda: 5)
    page.deep_ports = SimpleNamespace(get_value=lambda: 100)
    for field in ("hostname", "vendor", "os_hint", "deep_udp", "deep_versions", "deep_os", "deep_elevate"):
        setattr(page, field, SimpleNamespace(get_active=lambda: False))
    page._start_pulse = lambda: None
    page._scan_failed = lambda _: None
    queued = []
    page.tasks = SimpleNamespace(submit=lambda work, *_: queued.append(work))
    options = []
    page.service = SimpleNamespace(scan=lambda **kwargs: options.append(kwargs))
    page._start_scan(None)
    # An unrelated settings change must not alter a scan already queued.
    page.config.discovery.auto_register = True
    page.config.discovery.offline_after_seconds = 45
    queued[0]()
    assert options[0]["auto_register"] is False
    assert options[0]["offline_after_seconds"] == 120
