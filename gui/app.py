"""GTK4 application entry point for Linux."""
from __future__ import annotations

import sys

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

from core.config import load_config
from core.database import Database
from gui.window import NetFatherWindow


class NetFatherApplication(Gtk.Application):
    def __init__(self) -> None:
        super().__init__(application_id="org.praxis1071.NetFather")
        self.config = None
        self.database = None

    def do_activate(self) -> None:
        if self.config is None:
            self.config = load_config()
            self.database = Database(self.config.database_path)
            self.database.init_db()
        window = self.props.active_window
        if window is None:
            window = NetFatherWindow(self, self.config, self.database)
        window.present()


def main() -> int:
    return NetFatherApplication().run(sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
