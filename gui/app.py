"""GTK4 application entry point for Linux."""
from __future__ import annotations

import sys

import gi

gi.require_version("Gdk", "4.0")
gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, Gtk

from core.config import load_config
from core.database import Database
from gui.state import ApplicationState
from gui.tasks import BackgroundTaskRunner
from gui.window import NetFatherWindow


_APP_CSS = """
window {
    background: @window_bg_color;
}

.navigation-sidebar {
    padding: 18px 10px;
    background: alpha(@card_bg_color, 0.92);
    border-right: 1px solid alpha(@borders, 0.65);
}

.navigation-sidebar > row {
    min-height: 42px;
    margin: 2px 0;
    border-radius: 9px;
    padding: 0 10px;
}

.navigation-sidebar > row:selected {
    background: alpha(@accent_bg_color, 0.20);
    color: @accent_color;
}

.navigation-sidebar > row:hover:not(:selected) {
    background: alpha(@view_fg_color, 0.06);
}

.sidebar-brand {
    font-size: 20px;
    font-weight: 700;
    margin: 4px 10px 14px;
}

.page-shell {
    background: @window_bg_color;
}

.card {
    border-radius: 12px;
    border: 1px solid alpha(@borders, 0.70);
    background: alpha(@card_bg_color, 0.82);
    padding: 2px;
}

.metric-card {
    min-height: 112px;
}

.status-ok {
    color: @success_color;
}

.status-warning {
    color: @warning_color;
}

.status-error {
    color: @error_color;
}

.mono-value {
    font-family: monospace;
}
"""


class NetFatherApplication(Gtk.Application):
    """Own application-wide services while keeping pages view-focused."""

    def __init__(self) -> None:
        super().__init__(application_id="org.praxis1071.NetFather")
        self.config = None
        self.database = None
        self.state = ApplicationState()
        self.tasks = BackgroundTaskRunner()
        self._css_loaded = False

    def _load_css(self) -> None:
        if self._css_loaded:
            return
        display = Gdk.Display.get_default()
        if display is None:
            return
        provider = Gtk.CssProvider()
        provider.load_from_data(_APP_CSS.encode("utf-8"))
        Gtk.StyleContext.add_provider_for_display(
            display,
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )
        self._css_loaded = True

    def do_activate(self) -> None:
        self._load_css()
        if self.config is None:
            self.config = load_config()
            self.database = Database(self.config.database_path)
            self.database.init_db()

        window = self.props.active_window
        if window is None:
            window = NetFatherWindow(
                self,
                self.config,
                self.database,
                state=self.state,
                tasks=self.tasks,
            )
        window.present()

    def do_shutdown(self) -> None:
        self.tasks.shutdown()
        if self.database is not None:
            self.database.close()
        super().do_shutdown()


def main() -> int:
    return NetFatherApplication().run(sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
