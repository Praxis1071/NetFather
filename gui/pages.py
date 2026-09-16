"""GTK4 pages for the Linux application."""
from __future__ import annotations

from gi.repository import GLib, Gtk
from sqlalchemy import func, select

from core.config import Config
from core.database import Database
from gui.state import ApplicationState
from gui.tasks import BackgroundTaskRunner
from manager.device_manager import DeviceManager
from models.device import Device
from network.discovery_service import DiscoveryService, DiscoverySnapshot
from network.interface import get_network_status


class BasePage(Gtk.Box):
    def __init__(self, title: str, subtitle: str = "") -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self.set_margin_top(28)
        self.set_margin_bottom(28)
        self.set_margin_start(32)
        self.set_margin_end(32)
        heading = Gtk.Label(label=title, xalign=0)
        heading.add_css_class("title-1")
        self.append(heading)
        if subtitle:
            label = Gtk.Label(label=subtitle, xalign=0, wrap=True)
            label.add_css_class("dim-label")
            self.append(label)


def _section(title: str, child: Gtk.Widget) -> Gtk.Box:
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    heading = Gtk.Label(label=title, xalign=0)
    heading.add_css_class("heading")
    box.append(heading)
    box.append(child)
    return box


class DashboardPage(BasePage):
    def __init__(self, config: Config, database: Database, state: ApplicationState) -> None:
        super().__init__("Dashboard", "NetFather Linux network management")
        self.database = database
        self.state = state
        self.status = Gtk.Label(xalign=0, wrap=True)
        self.status.add_css_class("card")
        self.append(self.status)
        self.refresh()
        button = Gtk.Button(label="Refresh")
        button.set_halign(Gtk.Align.START)
        button.connect("clicked", lambda _b: self.refresh())
        self.append(button)

    def refresh(self) -> None:
        network = get_network_status()
        with self.database.session() as session:
            count = session.scalar(select(func.count(Device.id))) or 0
        self.state.network.interface = network.interface
        self.state.network.local_ip = network.local_ip
        self.state.network.gateway = network.gateway
        self.state.network.known_devices = count
        self.status.set_text(
            f"Interface: {network.interface or 'Unknown'}\n"
            f"Local IP: {network.local_ip or 'Unknown'}\n"
            f"Gateway: {network.gateway or 'Unknown'}\n"
            f"Registered devices: {count}"
        )


class DiscoveryPage(BasePage):
    """Responsive discovery workspace backed by DiscoveryService."""

    def __init__(
        self,
        config: Config,
        database: Database,
        state: ApplicationState,
        tasks: BackgroundTaskRunner,
    ) -> None:
        super().__init__("Network Discovery", "Discover and identify devices on the local Linux network.")
        self.config = config
        self.database = database
        self.state = state
        self.tasks = tasks
        self.service = DiscoveryService(device_manager=DeviceManager(database))
        self._pulse_source: int | None = None
        self._unsubscribe = self.state.subscribe(self._on_state_changed)

        self.summary = Gtk.Label(xalign=0, wrap=True)
        self.summary.add_css_class("dim-label")
        self.append(self.summary)

        options = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        options.add_css_class("card")

        mode_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        mode_label = Gtk.Label(label="Scan mode", xalign=0)
        mode_label.set_hexpand(True)
        mode_row.append(mode_label)
        self.mode = Gtk.ComboBoxText()
        for value in ("passive", "active", "hybrid"):
            self.mode.append(value, value.capitalize())
        self.mode.set_active_id(self.config.discovery.mode)
        mode_row.append(self.mode)
        options.append(mode_row)

        subnet_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        subnet_label = Gtk.Label(label="Subnet", xalign=0)
        subnet_label.set_hexpand(True)
        subnet_row.append(subnet_label)
        self.subnet = Gtk.Entry()
        self.subnet.set_placeholder_text("Auto-detect local subnet")
        self.subnet.set_text(self.config.discovery.subnet)
        self.subnet.set_width_chars(20)
        subnet_row.append(self.subnet)
        options.append(subnet_row)

        timeout_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        timeout_label = Gtk.Label(label="Command timeout (seconds)", xalign=0)
        timeout_label.set_hexpand(True)
        timeout_row.append(timeout_label)
        self.timeout = Gtk.SpinButton.new_with_range(1, 60, 1)
        self.timeout.set_value(self.config.network.scan_timeout_seconds)
        timeout_row.append(self.timeout)
        options.append(timeout_row)

        self.hostname = Gtk.CheckButton(label="Resolve hostnames")
        self.hostname.set_active(self.config.discovery.hostname_resolution)
        options.append(self.hostname)
        self.vendor = Gtk.CheckButton(label="Detect hardware vendor")
        self.vendor.set_active(self.config.discovery.vendor_detection)
        options.append(self.vendor)
        self.os_hint = Gtk.CheckButton(label="Estimate operating system")
        self.os_hint.set_active(self.config.discovery.os_detection)
        options.append(self.os_hint)

        expander = Gtk.Expander(label="Scan options")
        expander.set_child(options)
        expander.set_expanded(True)
        self.append(expander)

        controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.scan_button = Gtk.Button(label="Start scan")
        self.scan_button.add_css_class("suggested-action")
        self.scan_button.connect("clicked", self._start_scan)
        controls.append(self.scan_button)
        self.last_scan = Gtk.Label(label="No scan run yet", xalign=0)
        self.last_scan.add_css_class("dim-label")
        controls.append(self.last_scan)
        self.append(controls)

        self.progress = Gtk.ProgressBar()
        self.progress.set_show_text(True)
        self.progress.set_text("Ready")
        self.append(self.progress)

        self.status = Gtk.Label(label="Ready", xalign=0, wrap=True)
        self.append(self.status)

        self.device_list = Gtk.ListBox()
        self.device_list.set_selection_mode(Gtk.SelectionMode.NONE)
        self.device_list.set_vexpand(True)
        self.device_list.add_css_class("boxed-list")
        self.append(_section("Discovered devices", self.device_list))
        self._render_devices(self.state.discovery.identities)
        self._on_state_changed()

    def _start_scan(self, _button: Gtk.Button) -> None:
        if self.state.discovery.running:
            return
        mode = self.mode.get_active_id() or "hybrid"
        subnet = self.subnet.get_text().strip()
        timeout = int(self.timeout.get_value())
        hostname_resolution = self.hostname.get_active()
        vendor_detection = self.vendor.get_active()
        os_detection = self.os_hint.get_active()
        self.state.discovery.running = True
        self.state.discovery.mode = mode
        self.state.discovery.subnet = subnet
        self.state.discovery.hostname_resolution = hostname_resolution
        self.state.discovery.vendor_detection = vendor_detection
        self.state.discovery.os_detection = os_detection
        self.state.discovery.timeout_seconds = timeout
        self.state.discovery.error = None
        self.state.discovery.status_message = "Scanning local network..."
        self.state.notify_changed()
        self._start_pulse()

        self.tasks.submit(
            lambda: self.service.scan(
                timeout_seconds=timeout,
                active_timeout_seconds=self.config.discovery.active_timeout_seconds,
                mode=mode,
                subnet=subnet or None,
                hostname_resolution=hostname_resolution,
                vendor_detection=vendor_detection,
                os_detection=os_detection,
            ),
            self._scan_finished,
            self._scan_failed,
        )

    def _scan_finished(self, snapshot: DiscoverySnapshot) -> None:
        self.state.discovery.running = False
        self.state.discovery.scanned = snapshot.scanned
        self.state.discovery.identities = snapshot.identities
        self.state.discovery.error = snapshot.error
        if snapshot.error is None:
            self.state.discovery.status_message = (
                f"Scan completed: {snapshot.scanned} host(s) observed. "
                f"New {snapshot.new_devices}, updated {snapshot.updated_devices}, offline {snapshot.offline_devices}."
            )
        else:
            self.state.discovery.status_message = snapshot.error
        self.state.notify_changed()
        self._stop_pulse()
        self.last_scan.set_text(f"Completed at {snapshot.completed_at.astimezone().strftime('%H:%M:%S')}")

    def _scan_failed(self, error: BaseException) -> None:
        self.state.discovery.running = False
        self.state.discovery.error = str(error)
        self.state.discovery.status_message = str(error)
        self.state.notify_changed()
        self._stop_pulse()

    def _on_state_changed(self) -> None:
        discovery = self.state.discovery
        self.scan_button.set_sensitive(not discovery.running)
        self.progress.set_text("Scanning..." if discovery.running else ("Error" if discovery.error else "Ready"))
        self.status.set_text(discovery.status_message)
        online = sum(1 for identity in discovery.identities if identity.online)
        self.summary.set_text(
            f"Observed: {discovery.scanned}   |   Known identities: {len(discovery.identities)}   |   Online: {online}"
        )
        self._render_devices(discovery.identities)

    def _render_devices(self, identities) -> None:
        while (child := self.device_list.get_first_child()) is not None:
            self.device_list.remove(child)
        if not identities:
            empty = Gtk.Label(label="No devices discovered yet.", xalign=0)
            empty.add_css_class("dim-label")
            self.device_list.append(empty)
            return
        for identity in sorted(identities, key=lambda item: (not item.online, item.current_ip or item.mac)):
            row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
            row.set_margin_top(10)
            row.set_margin_bottom(10)
            row.set_margin_start(12)
            row.set_margin_end(12)
            title = Gtk.Label(label=f"{'Online' if identity.online else 'Offline'}  {identity.current_ip or 'No IP'}", xalign=0)
            title.add_css_class("heading")
            row.append(title)
            details = [identity.mac]
            if identity.hostnames:
                details.append(sorted(identity.hostnames)[0])
            if identity.vendors:
                details.append(sorted(identity.vendors)[0])
            if identity.os_hints:
                details.append(sorted(identity.os_hints)[0])
            details.append(f"Confidence {identity.confidence:.0%}")
            detail_label = Gtk.Label(label="  |  ".join(details), xalign=0, wrap=True)
            detail_label.add_css_class("dim-label")
            row.append(detail_label)
            self.device_list.append(row)

    def _start_pulse(self) -> None:
        if self._pulse_source is None:
            self._pulse_source = GLib.timeout_add(120, self._pulse_progress)

    def _pulse_progress(self) -> bool:
        if not self.state.discovery.running:
            self._pulse_source = None
            return GLib.SOURCE_REMOVE
        self.progress.pulse()
        return GLib.SOURCE_CONTINUE

    def _stop_pulse(self) -> None:
        if self._pulse_source is not None:
            GLib.source_remove(self._pulse_source)
            self._pulse_source = None
        self.progress.set_fraction(1.0 if not self.state.discovery.error else 0.0)


class DevicesPage(BasePage):
    def __init__(self, database: Database) -> None:
        super().__init__("Devices", "Registered devices and their current network identity.")
        self.database = database
        self.list_box = Gtk.ListBox()
        self.list_box.set_vexpand(True)
        self.list_box.add_css_class("boxed-list")
        self.append(self.list_box)
        button = Gtk.Button(label="Refresh devices")
        button.set_halign(Gtk.Align.START)
        button.connect("clicked", lambda _b: self.refresh())
        self.append(button)
        self.refresh()

    def refresh(self) -> None:
        while (child := self.list_box.get_first_child()) is not None:
            self.list_box.remove(child)
        with self.database.session() as session:
            devices = list(session.scalars(select(Device).order_by(Device.name)))
        if not devices:
            self.list_box.append(Gtk.Label(label="No registered devices yet.", xalign=0))
            return
        for device in devices:
            text = f"{device.name}   {device.ip or 'No IP'}   {device.mac}   {device.os_hint or 'Unknown'}"
            self.list_box.append(Gtk.Label(label=text, xalign=0))


class PlaceholderPage(BasePage):
    def __init__(self, title: str, message: str) -> None:
        super().__init__(title, message)
