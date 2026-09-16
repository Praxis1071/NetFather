"""Polished GTK4 dashboard for the NetFather control center."""
from __future__ import annotations

from gi.repository import GLib, Gtk

from core.database import Database
from gui.state import ApplicationState
from gui.tasks import BackgroundTaskRunner
from manager.policy_service import PolicyService, PolicySnapshot
from monitor.monitor import Monitor, TrafficSnapshot
from network.interface import get_network_status


class MetricCard(Gtk.Box):
    """Compact dashboard metric with a small status animation."""

    def __init__(self, title: str, value: str = "—", detail: str = "") -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.set_hexpand(True)
        self.add_css_class("card")
        self.add_css_class("metric-card")
        self.set_margin_top(2)
        self.set_margin_bottom(2)
        self.set_margin_start(2)
        self.set_margin_end(2)
        self.title = Gtk.Label(label=title, xalign=0)
        self.title.add_css_class("dim-label")
        self.value = Gtk.Label(label=value, xalign=0)
        self.value.add_css_class("title-2")
        self.detail = Gtk.Label(label=detail, xalign=0, wrap=True)
        self.detail.add_css_class("dim-label")
        for widget in (self.title, self.value, self.detail):
            widget.set_margin_start(14)
            widget.set_margin_end(14)
        self.title.set_margin_top(12)
        self.detail.set_margin_bottom(12)
        self.append(self.title)
        self.append(self.value)
        self.append(self.detail)

    def update(self, value: str, detail: str = "") -> None:
        self.value.set_text(value)
        self.detail.set_text(detail)


class DashboardPage(Gtk.Box):
    """Network control-center dashboard backed by real backend snapshots."""

    def __init__(self, database: Database, state: ApplicationState, tasks: BackgroundTaskRunner) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self.set_margin_top(28)
        self.set_margin_bottom(28)
        self.set_margin_start(32)
        self.set_margin_end(32)
        self.database = database
        self.state = state
        self.tasks = tasks
        self._busy = False
        self._pulse_source: int | None = None
        self._refresh_source: int | None = None

        heading = Gtk.Label(label="Dashboard", xalign=0)
        heading.add_css_class("title-1")
        self.append(heading)
        subtitle = Gtk.Label(
            label="A live overview of your local network, devices and effective access policy.",
            xalign=0,
            wrap=True,
        )
        subtitle.add_css_class("dim-label")
        self.append(subtitle)

        cards = Gtk.Grid(column_spacing=10, row_spacing=10)
        cards.set_hexpand(True)
        self.network_card = MetricCard("NETWORK", "Checking…")
        self.devices_card = MetricCard("DEVICES", "—")
        self.policy_card = MetricCard("POLICY", "—")
        self.traffic_card = MetricCard("TRAFFIC", "—")
        cards.attach(self.network_card, 0, 0, 1, 1)
        cards.attach(self.devices_card, 1, 0, 1, 1)
        cards.attach(self.policy_card, 2, 0, 1, 1)
        cards.attach(self.traffic_card, 3, 0, 1, 1)
        for index in range(4):
            cards.get_child_at(index, 0).set_hexpand(True)
        self.append(cards)

        activity = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        activity.add_css_class("card")
        self.activity_title = Gtk.Label(label="Network status", xalign=0)
        self.activity_title.add_css_class("heading")
        self.activity_status = Gtk.Label(label="Loading…", xalign=0, wrap=True)
        self.activity_status.add_css_class("dim-label")
        for widget in (self.activity_title, self.activity_status):
            widget.set_margin_start(14)
            widget.set_margin_end(14)
        self.activity_title.set_margin_top(14)
        self.activity_status.set_margin_bottom(14)
        activity.append(self.activity_title)
        activity.append(self.activity_status)
        self.append(activity)

        controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.refresh_button = Gtk.Button(label="Refresh now")
        self.refresh_button.add_css_class("suggested-action")
        self.refresh_button.connect("clicked", lambda _button: self.refresh())
        controls.append(self.refresh_button)
        self.refresh_status = Gtk.Label(label="Live refresh every 5 seconds", xalign=0)
        self.refresh_status.add_css_class("dim-label")
        controls.append(self.refresh_status)
        self.append(controls)
        self.refresh()
        self._refresh_source = GLib.timeout_add_seconds(5, self._scheduled_refresh)

    def _scheduled_refresh(self) -> bool:
        if self.get_root() is None:
            self._refresh_source = None
            return GLib.SOURCE_REMOVE
        self.refresh()
        return GLib.SOURCE_CONTINUE

    def refresh(self) -> None:
        if self._busy:
            return
        self._busy = True
        self.refresh_button.set_sensitive(False)
        self.refresh_status.set_text("Refreshing live network state…")
        self._start_pulse()
        self.tasks.submit(self._load_snapshot, self._loaded, self._failed)

    def _load_snapshot(self) -> tuple[PolicySnapshot, TrafficSnapshot, object]:
        policy = PolicyService(self.database).refresh()
        traffic = Monitor(self.database).snapshot()
        network = get_network_status()
        return policy, traffic, network

    def _loaded(self, result: tuple[PolicySnapshot, TrafficSnapshot, object]) -> None:
        policy, traffic, network = result
        self._busy = False
        self.refresh_button.set_sensitive(True)
        self._stop_pulse()
        self.network_card.update(
            "Connected" if network.interface else "Unavailable",
            f"{network.interface or 'No interface'}  •  {network.local_ip or 'No local IP'}",
        )
        self.devices_card.update(
            str(len(policy.devices)),
            f"{policy.online} online  •  {policy.allowed} allowed  •  {policy.blocked} blocked",
        )
        self.policy_card.update(
            "Protected" if policy.blocked else "Open",
            f"{policy.blocked} device policy block(s) active",
        )
        sent = self._format_bytes(traffic.bytes_sent)
        received = self._format_bytes(traffic.bytes_recv)
        self.traffic_card.update("Live", f"↑ {sent}  •  ↓ {received}")
        self.activity_status.set_text(
            f"Interface: {traffic.interface or 'Unknown'}\n"
            f"Packets: {traffic.packets_sent:,} sent / {traffic.packets_recv:,} received\n"
            f"Errors: {traffic.errors_in + traffic.errors_out:,}  •  Drops: {traffic.drops_in + traffic.drops_out:,}"
        )
        self.refresh_status.set_text("Live data updated just now")

    def _failed(self, error: BaseException) -> None:
        self._busy = False
        self.refresh_button.set_sensitive(True)
        self._stop_pulse()
        self.activity_status.set_text(f"Unable to refresh network state: {error}")
        self.refresh_status.set_text("Refresh failed — retrying automatically")

    def _start_pulse(self) -> None:
        if self._pulse_source is None:
            self._pulse_source = GLib.timeout_add(120, self._pulse)

    def _pulse(self) -> bool:
        if not self._busy:
            self._pulse_source = None
            return GLib.SOURCE_REMOVE
        self.refresh_button.set_opacity(0.65 if self.refresh_button.get_opacity() > 0.8 else 1.0)
        return GLib.SOURCE_CONTINUE

    def _stop_pulse(self) -> None:
        if self._pulse_source is not None:
            GLib.source_remove(self._pulse_source)
            self._pulse_source = None
        self.refresh_button.set_opacity(1.0)

    @staticmethod
    def _format_bytes(value: int) -> str:
        units = ("B", "KB", "MB", "GB", "TB")
        amount = float(max(0, value))
        for unit in units:
            if amount < 1024 or unit == units[-1]:
                return f"{amount:.1f} {unit}"
            amount /= 1024
        return f"{amount:.1f} TB"
