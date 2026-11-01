"""Real GTK/Libadwaita rendering and lifecycle tests under Xvfb.

Enable explicitly in a graphical session or the dedicated CI job.
"""
from __future__ import annotations
import os
from pathlib import Path
import threading
import time
import subprocess

import pytest

pytestmark = pytest.mark.skipif(os.environ.get("NETFATHER_GTK_TESTS") != "1", reason="GTK graphical session required")


def pump(GLib, seconds=.2):
    deadline = time.monotonic() + seconds
    context = GLib.MainContext.default()
    while time.monotonic() < deadline:
        while context.pending():
            context.iteration(False)
        time.sleep(.01)


@pytest.mark.parametrize("language,theme,width", [("en", "light", 1240), ("tr", "dark", 620), ("az", "system", 360)])
def test_all_workspaces_render_adapt_and_close_without_late_callbacks(tmp_path, language, theme, width):
    import gi
    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Adw, Gdk, Gio, GLib, Gtk
    from core.config import Config
    from core.database import Database
    from core.i18n import set_language
    from gui.state import ApplicationState
    from gui.tasks import BackgroundTaskRunner
    from gui.theme import ThemeController
    from gui.window import NetFatherWindow
    from manager.device_manager import DeviceManager
    from network.discovery import DiscoveredHost

    Adw.init()
    set_language(language)
    app = Adw.Application(application_id=f"org.praxis1071.NetFather.Test.{language}", flags=Gio.ApplicationFlags.NON_UNIQUE)
    app.register(None)
    config = Config(config_path=tmp_path / "config.toml")
    config.general.data_dir = str(tmp_path)
    config.discovery.live_presence_enabled = False
    db = Database(tmp_path / "gtk.db")
    db.init_db()
    DeviceManager(db).reconcile_discovery([DiscoveredHost("192.168.1.20", mac="02:00:00:00:00:20", hostname="Tablet", source="active")])
    tasks = BackgroundTaskRunner(max_workers=4)
    controller = ThemeController()
    controller.apply(theme)
    window = NetFatherWindow(app, config, db, state=ApplicationState(), tasks=tasks)
    window.set_default_size(width, 800)
    window.present()
    output = Path(os.environ.get("NETFATHER_SCREENSHOTS", str(tmp_path / "screenshots")))
    output.mkdir(parents=True, exist_ok=True)
    try:
        pump(GLib, 1)
        assert window.get_width() <= width + 30, (window.get_width(), width)
        assert window.split_view.get_collapsed() == (width < 900)
        for name, page in window.pages.items():
            window.workspace.set_visible_child_name(name)
            pump(GLib, .3)
            assert page.get_width() > 0
            assert page.get_width() <= window.get_width()
            subprocess.run(["scrot", "-o", str(output / f"{language}-{theme}-{width}-{name.replace(' ', '-')}.png")], check=True, timeout=5)
        # A queued delivery may exist when a window closes. Scope cancellation
        # must suppress it even when the worker itself already completed.
        delivered = []
        scope = window._scopes[0]
        scope.submit(lambda: "late", delivered.append, delivered.append)
        window.close()
        tasks.shutdown()
        pump(GLib, .3)
        assert delivered == []
        assert all(scope.closed for scope in window._scopes)
        if theme != "system":
            assert controller.manager.get_dark() == (theme == "dark")
        if os.environ.get("ADW_DEBUG_HIGH_CONTRAST") == "1":
            assert controller.manager.get_high_contrast()
    finally:
        window.close()
        tasks.shutdown()
        controller.cleanup()
        db.close()
        set_language("en")
