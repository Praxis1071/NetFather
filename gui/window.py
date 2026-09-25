"""Main GTK4 application window."""
from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

from core.config import Config, save_config
from core.database import Database
from core.privileges import detect_privileges
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


class NetFatherWindow(Gtk.ApplicationWindow):
    """Root window with a responsive, lightly animated GTK4 workspace."""

    def __init__(self, app: Gtk.Application, config: Config, database: Database, *, state: ApplicationState, tasks: BackgroundTaskRunner) -> None:
        super().__init__(application=app, title="NetFather")
        self.set_default_size(1240, 800)
        self.set_size_request(900, 620)
        self.set_child(self._build_ui(config, database, state, tasks))

    def _build_ui(self, config: Config, database: Database, state: ApplicationState, tasks: BackgroundTaskRunner) -> Gtk.Widget:
        root = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        root.add_css_class("page-shell")
        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        sidebar.set_size_request(220, -1)
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
            "Settings": self._settings_page(config),
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
            label = Gtk.Label(label=name, xalign=0)
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

    def _settings_page(self, config: Config) -> Gtk.Widget:
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        page.set_margin_top(28)
        page.set_margin_bottom(28)
        page.set_margin_start(32)
        page.set_margin_end(32)
        title = Gtk.Label(label="Settings", xalign=0)
        title.add_css_class("title-1")
        page.append(title)
        subtitle = Gtk.Label(label="Configure NetFather and learn more about the application.", xalign=0, wrap=True)
        subtitle.add_css_class("dim-label")
        page.append(subtitle)
        switcher = Gtk.StackSwitcher()
        switcher.set_halign(Gtk.Align.START)
        switcher.add_css_class("linked")
        page.append(switcher)
        stack = Gtk.Stack()
        stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        stack.set_transition_duration(160)
        switcher.set_stack(stack)
        page.append(stack)
        general = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        general.set_margin_top(14)
        general.append(self._section_title("General"))
        general_text = Gtk.Label(label="NetFather continuously watches the Linux neighbor table when live presence monitoring is enabled. Changes trigger a debounced discovery reconciliation so device state stays current without keeping a packet sniffer running.", xalign=0, wrap=True)
        general_text.add_css_class("dim-label")
        general.append(general_text)
        general.append(self._live_presence_card(config))
        general.append(self._privilege_card())
        stack.add_titled(general, "general", "General")
        about = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        about.set_margin_top(14)
        about.set_margin_bottom(8)
        about_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        about_card.add_css_class("card")
        about_card.set_margin_start(2)
        about_card.set_margin_end(2)
        about_card.set_margin_top(2)
        about_card.set_margin_bottom(2)
        app_name = Gtk.Label(label="NetFather", xalign=0)
        app_name.add_css_class("title-2")
        about_card.append(app_name)
        version = Gtk.Label(label="Version 0.5.0", xalign=0)
        version.add_css_class("dim-label")
        about_card.append(version)
        description = Gtk.Label(label="Linux için yerel ağ cihaz keşfi, izleme, profil, zamanlama ve erişim yönetimi uygulaması.", xalign=0, wrap=True)
        about_card.append(description)
        developer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        developer_label = Gtk.Label(label="Developer", xalign=0)
        developer_label.add_css_class("dim-label")
        developer.append(developer_label)
        developer_name = Gtk.Label(label="Praxis1071", xalign=0)
        developer_name.add_css_class("heading")
        developer.append(developer_name)
        about_card.append(developer)
        github = Gtk.LinkButton(uri="https://github.com/Praxis1071", label="GitHub profile")
        github.set_halign(Gtk.Align.START)
        about_card.append(github)
        project = Gtk.LinkButton(uri="https://github.com/Praxis1071/NetFather", label="NetFather repository")
        project.set_halign(Gtk.Align.START)
        about_card.append(project)
        about.append(about_card)
        stack.add_titled(about, "about", "About")
        stack.set_visible_child_name("general")
        return page

    def _live_presence_card(self, config: Config) -> Gtk.Widget:
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        card.add_css_class("card")
        title = Gtk.Label(label="Live network presence", xalign=0)
        title.add_css_class("title-2")
        card.append(title)
        description = Gtk.Label(label="Uses Linux neighbor-table notifications as the fast path and periodic hybrid discovery as a safety net. It does not require root and does not run a continuous packet capture.", xalign=0, wrap=True)
        description.add_css_class("dim-label")
        card.append(description)
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        label = Gtk.Label(label="Monitor network presence automatically", xalign=0)
        label.set_hexpand(True)
        row.append(label)
        enabled = Gtk.Switch()
        enabled.set_active(config.discovery.live_presence_enabled)
        row.append(enabled)
        card.append(row)
        interval_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        interval_label = Gtk.Label(label="Safety discovery interval (seconds)", xalign=0)
        interval_label.set_hexpand(True)
        interval_row.append(interval_label)
        interval = Gtk.SpinButton.new_with_range(3, 300, 1)
        interval.set_value(config.discovery.live_presence_interval_seconds)
        interval_row.append(interval)
        card.append(interval_row)
        status = Gtk.Label(xalign=0, wrap=True)
        status.add_css_class("dim-label")
        card.append(status)
        def apply_settings(_widget: Gtk.Widget) -> None:
            config.discovery.live_presence_enabled = enabled.get_active()
            config.discovery.live_presence_interval_seconds = int(interval.get_value())
            save_config(config)
            app = self.get_application()
            service = getattr(app, "live_presence", None)
            if service is not None:
                service.interval_seconds = max(3, config.discovery.live_presence_interval_seconds)
                if config.discovery.live_presence_enabled:
                    service.start()
                    status.set_text("Live presence monitoring is enabled.")
                else:
                    service.stop()
                    status.set_text("Live presence monitoring is disabled.")
        enabled.connect("state-set", lambda *_args: (apply_settings(enabled), False)[1])
        interval.connect("value-changed", apply_settings)
        status.set_text("Enabled" if enabled.get_active() else "Disabled")
        return card

    @staticmethod
    def _privilege_card() -> Gtk.Widget:
        status = detect_privileges()
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        card.add_css_class("card")
        card.set_margin_top(4)
        title = Gtk.Label(label="Network capabilities", xalign=0)
        title.add_css_class("title-2")
        card.append(title)
        description = Gtk.Label(label="NetFather keeps the GTK interface unprivileged. Elevated access is exposed as a capability for operations that genuinely require it.", xalign=0, wrap=True)
        description.add_css_class("dim-label")
        card.append(description)
        summary = Gtk.Label(label=status.summary, xalign=0)
        summary.add_css_class("status-ok" if status.can_run_privileged_operations else "status-warning")
        card.append(summary)
        for label, available in (("pkexec", status.pkexec_available), ("nftables", status.nft_available), ("iproute2", status.ip_available), ("NetworkManager", status.network_manager_available)):
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            marker = Gtk.Label(label="Available" if available else "Unavailable", xalign=0)
            marker.add_css_class("status-ok" if available else "status-warning")
            name = Gtk.Label(label=label, xalign=0)
            name.set_hexpand(True)
            row.append(name)
            row.append(marker)
            card.append(row)
        note = Gtk.Label(label="Privileged actions will use a narrow system service and polkit authorization instead of relaunching the whole GUI as root.", xalign=0, wrap=True)
        note.add_css_class("dim-label")
        card.append(note)
        return card

    @staticmethod
    def _section_title(text: str) -> Gtk.Label:
        label = Gtk.Label(label=text, xalign=0)
        label.add_css_class("title-2")
        return label
