"""Main GTK4 window and navigation shell."""
from __future__ import annotations

from gi.repository import Gtk

from core.config import Config
from core.database import Database
from gui.pages import DashboardPage, DevicesPage, DiscoveryPage, PlaceholderPage


class NetFatherWindow(Gtk.ApplicationWindow):
    def __init__(self, app: Gtk.Application, config: Config, database: Database) -> None:
        super().__init__(application=app)
        self.set_title("NetFather")
        self.set_default_size(1200, 760)
        self.config = config
        self.database = database

        root = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self.set_child(root)
        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        sidebar.set_size_request(240, -1)
        sidebar.set_margin_top(24); sidebar.set_margin_bottom(24); sidebar.set_margin_start(16); sidebar.set_margin_end(16)
        root.append(sidebar)
        brand = Gtk.Label(label="NETFATHER", xalign=0)
        brand.add_css_class("title-2")
        sidebar.append(brand)
        subtitle = Gtk.Label(label="Linux network management", xalign=0)
        subtitle.add_css_class("dim-label")
        sidebar.append(subtitle)
        nav = Gtk.ListBox()
        nav.set_selection_mode(Gtk.SelectionMode.SINGLE)
        nav.add_css_class("navigation-sidebar")
        sidebar.append(nav)

        self.stack = Gtk.Stack(hexpand=True, vexpand=True)
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        root.append(self.stack)
        self.pages = {
            "Dashboard": DashboardPage(config, database),
            "Discovery": DiscoveryPage(config, database),
            "Devices": DevicesPage(database),
            "Network Topology": PlaceholderPage("Network Topology", "Live network topology will be connected next."),
            "Profiles": PlaceholderPage("Profiles", "Device profiles and access policies will be managed here."),
            "Rules": PlaceholderPage("Rules", "Schedules and policy rules will be managed here."),
            "Monitoring": PlaceholderPage("Monitoring", "Live traffic and device activity will appear here."),
            "Events": PlaceholderPage("Events", "Network, policy and firewall events will appear here."),
            "Settings": PlaceholderPage("Settings", "GTK4 application settings will be connected here."),
        }
        for name, page in self.pages.items():
            self.stack.add_named(page, name)
            row = Gtk.ListBoxRow()
            label = Gtk.Label(label=name, xalign=0)
            label.set_margin_top(10); label.set_margin_bottom(10); label.set_margin_start(10); label.set_margin_end(10)
            row.set_child(label)
            row.set_name(name)
            nav.append(row)
        nav.connect("row-selected", self._on_navigation_selected)
        nav.select_row(nav.get_row_at_index(0))

    def _on_navigation_selected(self, _list: Gtk.ListBox, row: Gtk.ListBoxRow | None) -> None:
        if row is None:
            return
        name = row.get_name()
        self.stack.set_visible_child_name(name)
        self.set_title(f"NetFather — {name}")
