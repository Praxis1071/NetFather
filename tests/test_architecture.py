"""Repository architecture regression checks."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_gtk_pages_have_dedicated_modules() -> None:
    gui = ROOT / "gui"
    assert not (gui / "pages.py").exists()
    for name in (
        "base_page.py",
        "dashboard_page.py",
        "devices_page.py",
        "discovery_page.py",
        "events_page.py",
        "monitoring_page.py",
        "profiles_page.py",
        "rules_page.py",
        "topology_page.py",
    ):
        assert (gui / name).is_file(), name


def test_retired_cli_tui_trees_are_absent() -> None:
    assert not (ROOT / "cli").exists()
    assert not (ROOT / "tui").exists()


def test_stateful_pages_expose_cleanup_hooks() -> None:
    root = ROOT / "gui"
    for name in ("base_page.py", "discovery_page.py", "devices_page.py"):
        text = (root / name).read_text(encoding="utf-8")
        assert "def cleanup(" in text, name
    window = (root / "window.py").read_text(encoding="utf-8")
    assert 'connect("close-request", self._on_close_request)' in window
    assert "cleanup()" in window
