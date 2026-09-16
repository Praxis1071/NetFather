from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_retired_cli_and_tui_packages_are_absent() -> None:
    assert not (ROOT / "cli").exists()
    assert not (ROOT / "tui").exists()


def test_runtime_targets_are_linux_only() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "Operating System :: POSIX :: Linux" in pyproject
    assert "project.scripts" not in pyproject


def test_gui_entrypoint_is_gtk4_application() -> None:
    app = (ROOT / "gui" / "app.py").read_text(encoding="utf-8")
    assert "Gtk.Application" in app
