"""Initial GTK4 pages for the Linux application."""
from __future__ import annotations

import threading

from gi.repository import GLib, Gtk
from sqlalchemy import select, func

from core.config import Config
from core.database import Database
from models.device import Device
from network.discovery import scan_network
from network.interface import get_network_status


class BasePage(Gtk.Box):
    def __init__(self, title: str, subtitle: str = "") -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self.title = title
        self.set_margin_top(28); self.set_margin_bottom(28); self.set_margin_start(32); self.set_margin_end(32)
        heading = Gtk.Label(label=title, xalign=0)
        heading.add_css_class("title-1")
        self.append(heading)
        if subtitle:
            label = Gtk.Label(label=subtitle, xalign=0, wrap=True)
            label.add_css_class("dim-label")
            self.append(label)


class DashboardPage(BasePage):
    def __init__(self, config: Config, database: Database) -> None:
        super().__init__("Dashboard", "NetFather Linux network management")
        self.database = database
        self.config = config
        self.status = Gtk.Label(xalign=0, wrap=True)
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
        self.status.set_text(f"Interface: {network.interface or 'Unknown'}\nLocal IP: {network.local_ip or 'Unknown'}\nGateway: {network.gateway or 'Unknown'}\nRegistered devices: {count}")


class DiscoveryPage(BasePage):
    def __init__(self, config: Config, database: Database) -> None:
        super().__init__("Network Discovery", "Discover and identify devices on the local Linux network.")
        self.config = config
        self.database = database
        self.progress = Gtk.ProgressBar()
        self.progress.set_show_text(True)
        self.append(self.progress)
        self.status = Gtk.Label(label="Ready", xalign=0, wrap=True)
        self.append(self.status)
        self.scan_button = Gtk.Button(label="Start Scan")
        self.scan_button.set_halign(Gtk.Align.START)
        self.scan_button.connect("clicked", self._start_scan)
        self.append(self.scan_button)

    def _start_scan(self, _button: Gtk.Button) -> None:
        self.scan_button.set_sensitive(False)
        self.progress.set_fraction(0.1)
        self.status.set_text("Scanning local network…")
        thread = threading.Thread(target=self._scan_worker, daemon=True)
        thread.start()

    def _scan_worker(self) -> None:
        try:
            hosts = scan_network(
                timeout_seconds=self.config.network.scan_timeout_seconds,
                active_timeout_seconds=self.config.discovery.active_timeout_seconds,
                mode=self.config.discovery.mode,
                subnet=self.config.discovery.subnet or None,
                hostname_resolution=self.config.discovery.hostname_resolution,
                vendor_detection=self.config.discovery.vendor_detection,
                os_detection=self.config.discovery.os_detection,
            )
            GLib.idle_add(self._scan_finished, len(hosts), None)
        except Exception as exc:  # noqa: BLE001
            GLib.idle_add(self._scan_finished, 0, str(exc))

    def _scan_finished(self, count: int, error: str | None) -> bool:
        self.progress.set_fraction(1.0 if error is None else 0.0)
        self.status.set_text(error or f"Scan completed. Devices found: {count}")
        self.scan_button.set_sensitive(True)
        return False


class DevicesPage(BasePage):
    def __init__(self, database: Database) -> None:
        super().__init__("Devices", "Registered devices and their current network identity.")
        self.database = database
        self.list_box = Gtk.ListBox()
        self.list_box.set_vexpand(True)
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
