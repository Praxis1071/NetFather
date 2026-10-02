"""Main GTK4 application window."""
from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

from core.config import Config
from core.database import Database
from gui.dashboard_page import DashboardPage
from gui.events_page import EventsPage
from gui.monitoring_page import MonitoringPage
from gui.devices_page import DevicesPage
from gui.discovery_page import DiscoveryPage
from gui.profiles_page import ProfilesPage
from gui.rules_page import RulesPage
from gui.state import ApplicationState
from gui.tasks import BackgroundTaskRunner
from gui.topology_page import TopologyPage
from gui.settings_page import SettingsPage
from core.i18n import tr


class NetFatherWindow(Gtk.ApplicationWindow):
    """Root window with a responsive, lightly animated GTK4 workspace."""

    def __init__(self, app: Gtk.Application, config: Config, database: Database, *, state: ApplicationState, tasks: BackgroundTaskRunner) -> None:
        super().__init__(application=app, title="NetFather")
        self.set_default_size(1240, 800)
        self.set_size_request(620, 480)
        header = Gtk.HeaderBar()
        self.sidebar_toggle = Gtk.ToggleButton(icon_name="sidebar-show-symbolic")
        self.sidebar_toggle.set_active(True)
        self.sidebar_toggle.set_tooltip_text(tr("Show or hide navigation"))
        self.sidebar_toggle.connect("toggled", lambda button: self._sidebar.set_visible(button.get_active()))
        header.pack_start(self.sidebar_toggle)
        self.set_titlebar(header)
        self.set_child(self._build_ui(config, database, state, tasks))

    def _build_ui(self, config: Config, database: Database, state: ApplicationState, tasks: BackgroundTaskRunner) -> Gtk.Widget:
        root = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        root.add_css_class("page-shell")
        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self._sidebar = sidebar
        sidebar.set_size_request(200, -1)
        sidebar.add_css_class("navigation-sidebar")
        brand = Gtk.Label(label="NetFather", xalign=0)
        brand.add_css_class("sidebar-brand")
        sidebar.append(brand)
        navigation = Gtk.ListBox()
        navigation.set_selection_mode(Gtk.SelectionMode.SINGLE)
        navigation.add_css_class("navigation-sidebar")
        navigation.set_vexpand(True)
        sidebar.append(navigation)
        content = Gtk.Stack()
        content.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        content.set_transition_duration(180)
        content.set_hexpand(True)
        content.set_vexpand(True)
        pages = {
            "Dashboard": DashboardPage(database, state, tasks),
            "Discovery": DiscoveryPage(config, database, state, tasks),
            "Devices": DevicesPage(database, state, tasks),
            "Network Topology": TopologyPage(database, tasks),
            "Profiles": ProfilesPage(database, tasks),
            "Rules": RulesPage(database, tasks),
            "Monitoring": MonitoringPage(database, tasks),
            "Events": EventsPage(database, tasks),
            "Settings": SettingsPage(config, self.get_application()),
        }
        self._pages = tuple(pages.values())
        self.connect("close-request", self._on_close_request)
        for name, page in pages.items():
            scroller = Gtk.ScrolledWindow()
            scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            scroller.set_hexpand(True)
            scroller.set_vexpand(True)
            scroller.set_child(page)
            content.add_named(scroller, name)
            row = Gtk.ListBoxRow()
            label = Gtk.Label(label=tr(name), xalign=0)
            row.set_child(label)
            row.set_name(name)
            navigation.append(row)
        def on_selected(_list: Gtk.ListBox, row: Gtk.ListBoxRow | None) -> None:
            if row is not None:
                content.set_visible_child_name(row.get_name())
        navigation.connect("row-selected", on_selected)
        navigation.select_row(navigation.get_row_at_index(0))
        root.append(sidebar)
        root.append(content)
        return root

    def _on_close_request(self, _window: Gtk.Window) -> bool:
        for page in getattr(self, "_pages", ()):
            cleanup = getattr(page, "cleanup", None)
            if cleanup is not None:
                cleanup()
        return False
