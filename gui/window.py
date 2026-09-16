"""Main GTK4 application window."""
from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

from core.config import Config
from core.database import Database
from gui.pages import DashboardPage, DevicesPage, DiscoveryPage, PlaceholderPage
from gui.profiles_page import ProfilesPage
from gui.rules_page import RulesPage
from gui.state import ApplicationState
from gui.tasks import BackgroundTaskRunner
from gui.topology_page import TopologyPage


class NetFatherWindow(Gtk.ApplicationWindow):
    def __init__(self, app: Gtk.Application, config: Config, database: Database, *, state: ApplicationState, tasks: BackgroundTaskRunner) -> None:
        super().__init__(application=app, title="NetFather")
        self.set_default_size(1200, 760)
        self.set_size_request(900, 620)
        self.set_child(self._build_ui(config, database, state, tasks))

    def _build_ui(self, config: Config, database: Database, state: ApplicationState, tasks: BackgroundTaskRunner) -> Gtk.Widget:
        root = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        sidebar = Gtk.ListBox()
        sidebar.set_selection_mode(Gtk.SelectionMode.SINGLE)
        sidebar.set_size_request(210, -1)
        sidebar.add_css_class("navigation-sidebar")
        content = Gtk.Stack()
        content.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        content.set_transition_duration(160)
        content.set_hexpand(True)
        content.set_vexpand(True)

        pages = {
            "Dashboard": DashboardPage(config, database, state),
            "Discovery": DiscoveryPage(config, database, state, tasks),
            "Devices": DevicesPage(database, state, tasks),
            "Network Topology": TopologyPage(database, tasks),
            "Profiles": ProfilesPage(database, tasks),
            "Rules": RulesPage(database, tasks),
            "Monitoring": PlaceholderPage("Monitoring", "Live traffic and device activity will appear here."),
            "Events": PlaceholderPage("Events", "Policy and network events will appear here."),
            "Settings": PlaceholderPage("Settings", "Application settings will be managed here."),
        }
        for name, page in pages.items():
            content.add_named(page, name)
            row = Gtk.ListBoxRow()
            row.set_child(Gtk.Label(label=name, xalign=0))
            row.set_name(name)
            sidebar.append(row)

        def on_selected(_list: Gtk.ListBox, row: Gtk.ListBoxRow | None) -> None:
            if row is not None:
                content.set_visible_child_name(row.get_name())

        sidebar.connect("row-selected", on_selected)
        sidebar.select_row(sidebar.get_row_at_index(0))
        root.append(sidebar)
        root.append(content)
        return root
