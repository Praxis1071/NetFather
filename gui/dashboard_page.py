"""Polished GTK4 dashboard for the NetFather control center."""
from __future__ import annotations

from core.i18n import tr

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

        heading = Gtk.Label(label=tr('Dashboard'), xalign=0)
        heading.add_css_class("title-1")
        self.append(heading)
        subtitle = Gtk.Label(
            label=tr('A live overview of your local network, devices and effective access policy.'),
            xalign=0,
            wrap=True,
        )
        subtitle.add_css_class("dim-label")
        self.append(subtitle)

        cards = Gtk.Grid(column_spacing=10, row_spacing=10)
        cards.set_hexpand(True)
        self.network_card = MetricCard(tr('NETWORK'), tr('Checking…'))
        self.devices_card = MetricCard(tr('DEVICES'), "—")
        self.policy_card = MetricCard(tr('POLICY'), "—")
        self.traffic_card = MetricCard(tr('TRAFFIC'), "—")
        cards.attach(self.network_card, 0, 0, 1, 1)
        cards.attach(self.devices_card, 1, 0, 1, 1)
        cards.attach(self.policy_card, 0, 1, 1, 1)
        cards.attach(self.traffic_card, 1, 1, 1, 1)
        self.append(cards)

        activity = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        activity.add_css_class("card")
        self.activity_title = Gtk.Label(label=tr('Network status'), xalign=0)
        self.activity_title.add_css_class("heading")
        self.activity_status = Gtk.Label(label=tr('Loading…'), xalign=0, wrap=True)
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
        self.refresh_button = Gtk.Button(label=tr('Refresh now'))
        self.refresh_button.add_css_class("suggested-action")
        self.refresh_button.connect("clicked", lambda _button: self.refresh())
        controls.append(self.refresh_button)
        self.refresh_status = Gtk.Label(label=tr('Live refresh every 5 seconds'), xalign=0)
        self.refresh_status.add_css_class("dim-label")
        controls.append(self.refresh_status)
        self.append(controls)
        self.refresh()
        self._refresh_source = GLib.timeout_add_seconds(5, self._scheduled_refresh)

    def _scheduled_refresh(self) -> bool:
        """Refresh while the page remains attached to a live GTK window."""
        self._refresh_source = None
        if self.get_root() is None:
            return GLib.SOURCE_REMOVE
        self.refresh()
        self._refresh_source = GLib.timeout_add_seconds(5, self._scheduled_refresh)
        return GLib.SOURCE_REMOVE

    def cleanup(self) -> None:
        """Stop page-owned GTK timers when the window closes."""
        if self._refresh_source is not None:
            GLib.source_remove(self._refresh_source)
            self._refresh_source = None
        self._stop_pulse()

    def refresh(self) -> None:
        if self._busy:
            return
        self._busy = True
        self.refresh_button.set_sensitive(False)
        self.refresh_status.set_text(tr('Refreshing live network state…'))
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
            tr('Connected') if network.interface else tr('Unavailable'),
            f"{network.interface or tr('No interface')}  •  {network.local_ip or tr('No local IP')}",
        )
        self.devices_card.update(
            str(len(policy.devices)),
            tr('{v0} online  •  {v1} allowed  •  {v2} blocked', v0=policy.online, v1=policy.allowed, v2=policy.blocked),
        )
        self.policy_card.update(
            tr('Restricted policy') if policy.blocked else tr('Allow policy'),
            tr('{v0} device policy block(s) active', v0=policy.blocked),
        )
        sent = self._format_bytes(traffic.bytes_sent)
        received = self._format_bytes(traffic.bytes_recv)
        self.traffic_card.update(tr('Live'), f"↑ {sent}  •  ↓ {received}")
        self.activity_status.set_text(
            tr('Interface: {v0}\nPackets: {v1:,} sent / {v2:,} received\nErrors: {v3:,}  •  Drops: {v4:,}', v0=traffic.interface or tr('Unknown'), v1=traffic.packets_sent, v2=traffic.packets_recv, v3=traffic.errors_in + traffic.errors_out, v4=traffic.drops_in + traffic.drops_out)
        )
        self.refresh_status.set_text(tr('Live data updated just now'))

    def _failed(self, error: BaseException) -> None:
        self._busy = False
        self.refresh_button.set_sensitive(True)
        self._stop_pulse()
        self.activity_status.set_text(tr('Unable to refresh network state: {v0}', v0=error))
        self.refresh_status.set_text(tr('Refresh failed — retrying automatically'))

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
