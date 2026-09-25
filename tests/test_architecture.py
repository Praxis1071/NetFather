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
