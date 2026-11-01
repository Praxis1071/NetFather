"""Main GTK4 application window."""
from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk, GObject, Gio, GLib, Pango

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


class NetFatherWindow(Adw.ApplicationWindow):
    """Root window with a responsive, lightly animated GTK4 workspace."""

    def __init__(self, app: Gtk.Application, config: Config, database: Database, *, state: ApplicationState, tasks: BackgroundTaskRunner) -> None:
        super().__init__(application=app, title="NetFather")
        self.set_default_size(1240, 800)
        self.set_size_request(360, 480)
        self._scopes = []
        header = Adw.HeaderBar()
        self.sidebar_toggle = Gtk.ToggleButton(icon_name="sidebar-show-symbolic")
        self.sidebar_toggle.set_active(True)
        self.sidebar_toggle.set_tooltip_text(tr("Show or hide navigation"))
        header.pack_start(self.sidebar_toggle)
        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(header)
        toolbar.set_content(self._build_ui(config, database, state, tasks))
        self.set_content(toolbar)
        self.sidebar_toggle.bind_property("active", self.split_view, "show-sidebar", GObject.BindingFlags.BIDIRECTIONAL | GObject.BindingFlags.SYNC_CREATE)
        breakpoint = Adw.Breakpoint.new(Adw.BreakpointCondition.parse("max-width: 900sp"))
        breakpoint.add_setter(self.split_view, "collapsed", True)
        breakpoint.add_setter(self.split_view, "show-sidebar", False)
        self.add_breakpoint(breakpoint)
        action = Gio.SimpleAction.new("workspace", GLib.VariantType.new("s"))
        action.connect("activate", lambda _action, value: self.workspace.set_visible_child_name(value.get_string()))
        self.add_action(action)
        for index, name in enumerate(self.pages, 1):
            app.set_accels_for_action(Gio.Action.print_detailed_name("win.workspace", GLib.Variant("s", name)),
                                     [f"<Primary>{index}"])
        self._adapt_text(self)

    def _adapt_text(self, widget):
        if isinstance(widget, Gtk.Label):
            widget.set_wrap(True)
            widget.set_max_width_chars(80)
        if isinstance(widget, Gtk.ComboBox):
            for cell in widget.get_cells():
                cell.set_property("ellipsize", Pango.EllipsizeMode.END)
                cell.set_property("max-width-chars", 22)
        child = widget.get_first_child()
        while child is not None:
            self._adapt_text(child)
            child = child.get_next_sibling()

    def _build_ui(self, config: Config, database: Database, state: ApplicationState, tasks: BackgroundTaskRunner) -> Gtk.Widget:
        root = Adw.OverlaySplitView()
        self.split_view = root
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
        def scoped():
            scope = tasks.scope()
            self._scopes.append(scope)
            return scope
        pages = {
            "Dashboard": DashboardPage(database, state, scoped()),
            "Discovery": DiscoveryPage(config, database, state, scoped()),
            "Devices": DevicesPage(database, state, scoped()),
            "Network Topology": TopologyPage(database, scoped()),
            "Profiles": ProfilesPage(database, scoped()),
            "Rules": RulesPage(database, scoped()),
            "Monitoring": MonitoringPage(database, scoped()),
            "Events": EventsPage(database, scoped()),
            "Settings": SettingsPage(config, self.get_application()),
        }
        self._pages = tuple(pages.values())
        self.pages = pages
        self.workspace = content
        self.connect("close-request", self._on_close_request)
        for name, page in pages.items():
            scroller = Gtk.ScrolledWindow()
            scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            scroller.set_hexpand(True)
            scroller.set_vexpand(True)
            clamp = Adw.Clamp(maximum_size=1100, tightening_threshold=800)
            clamp.set_child(page)
            scroller.set_child(clamp)
            content.add_named(scroller, name)
            row = Gtk.ListBoxRow()
            label = Gtk.Label(label=tr(name), xalign=0)
            row.set_child(label)
            row.set_name(name)
            navigation.append(row)
        def on_selected(_list: Gtk.ListBox, row: Gtk.ListBoxRow | None) -> None:
            if row is not None:
                content.set_visible_child_name(row.get_name())
                if root.get_collapsed():
                    root.set_show_sidebar(False)
        navigation.connect("row-selected", on_selected)
        navigation.select_row(navigation.get_row_at_index(0))
        root.set_sidebar(sidebar)
        root.set_content(content)
        return root

    def _on_close_request(self, _window: Gtk.Window) -> bool:
        for scope in self._scopes:
            scope.close()
        for page in getattr(self, "_pages", ()):
            cleanup = getattr(page, "cleanup", None)
            if cleanup is not None:
                cleanup()
        return False
