"""Live GTK4 monitoring workspace."""
from __future__ import annotations

from core.i18n import tr

from datetime import datetime
from gi.repository import GLib, Gtk

from core.database import Database
from gui.tasks import BackgroundTaskRunner
from manager.policy_service import PolicyService
from monitor.monitor import Monitor, TrafficSnapshot


class MonitoringPage(Gtk.Box):
    def __init__(self, database: Database, tasks: BackgroundTaskRunner) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self.set_margin_top(28); self.set_margin_bottom(28); self.set_margin_start(32); self.set_margin_end(32)
        self.database = database; self.tasks = tasks; self._busy = False; self._paused = False; self._timer: int | None = None

        title = Gtk.Label(label=tr('Monitoring'), xalign=0); title.add_css_class("title-1"); self.append(title)
        subtitle = Gtk.Label(label=tr('Live interface counters and effective policy activity. Monitoring is observation-only.'), xalign=0, wrap=True); subtitle.add_css_class("dim-label"); self.append(subtitle)

        self.status = Gtk.Label(label=tr('Starting monitor…'), xalign=0, wrap=True); self.status.add_css_class("card"); self.append(self.status)
        grid = Gtk.Grid(column_spacing=10, row_spacing=10); grid.set_hexpand(True)
        self.sent = self._metric(grid, tr('Sent'), 0, 0); self.received = self._metric(grid, tr('Received'), 1, 0)
        self.packets = self._metric(grid, tr('Packets'), 2, 0); self.errors = self._metric(grid, tr('Errors / Drops'), 3, 0)
        self.allowed = self._metric(grid, tr('Allowed devices'), 0, 1); self.blocked = self._metric(grid, tr('Blocked devices'), 1, 1)
        self.updated = self._metric(grid, tr('Last update'), 2, 1); self.source = self._metric(grid, tr('Interface'), 3, 1)
        self.append(grid)

        controls = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.pause_button = Gtk.Button(label=tr('Pause live refresh')); self.pause_button.connect("clicked", self._toggle_pause); controls.append(self.pause_button)
        self.refresh_button = Gtk.Button(label=tr('Refresh now')); self.refresh_button.connect("clicked", lambda _b: self.refresh()); controls.append(self.refresh_button)
        self.live_label = Gtk.Label(label=tr('Live refresh: every 2 seconds'), xalign=0); self.live_label.add_css_class("dim-label"); controls.append(self.live_label)
        self.append(controls)
        self.refresh(); self._timer = GLib.timeout_add(2000, self._scheduled_refresh)

    @staticmethod
    def _metric(grid: Gtk.Grid, title: str, col: int, row: int) -> Gtk.Label:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4); box.add_css_class("card"); box.set_hexpand(True)
        heading = Gtk.Label(label=title, xalign=0); heading.add_css_class("dim-label"); value = Gtk.Label(label="—", xalign=0); value.add_css_class("title-2")
        for widget in (heading, value): widget.set_margin_start(14); widget.set_margin_end(14)
        heading.set_margin_top(12); value.set_margin_bottom(12); box.append(heading); box.append(value); grid.attach(box, col % 2, row * 2 + col // 2, 1, 1)
        return value

    def _scheduled_refresh(self) -> bool:
        """Refresh periodically unless paused or detached from the window."""
        self._timer = None
        if self.get_root() is None:
            return GLib.SOURCE_REMOVE
        if not self._paused:
            self.refresh()
        self._timer = GLib.timeout_add(2000, self._scheduled_refresh)
        return GLib.SOURCE_REMOVE

    def cleanup(self) -> None:
        """Stop the live-refresh timer when the window closes."""
        if self._timer is not None:
            GLib.source_remove(self._timer)
            self._timer = None

    def refresh(self) -> None:
        if self._busy: return
        self._busy = True; self.refresh_button.set_sensitive(False); self.tasks.submit(self._load, self._loaded, self._failed)

    def _load(self) -> tuple[TrafficSnapshot, object]:
        return Monitor(self.database).snapshot(), PolicyService(self.database).refresh()

    def _loaded(self, result: tuple[TrafficSnapshot, object]) -> None:
        traffic, policy = result; self._busy = False; self.refresh_button.set_sensitive(True)
        self.sent.set_text(self._format_bytes(traffic.bytes_sent)); self.received.set_text(self._format_bytes(traffic.bytes_recv))
        self.packets.set_text(f"{traffic.packets_sent:,} / {traffic.packets_recv:,}")
        self.errors.set_text(f"{traffic.errors_in + traffic.errors_out:,} / {traffic.drops_in + traffic.drops_out:,}")
        self.allowed.set_text(str(policy.allowed)); self.blocked.set_text(str(policy.blocked)); self.updated.set_text(datetime.now().astimezone().strftime("%H:%M:%S")); self.source.set_text(traffic.interface or tr('Unknown'))
        self.status.set_text(tr('Monitoring is active. Counters are read from the Linux network interface; policy state comes from the shared policy service.'))

    def _failed(self, error: BaseException) -> None:
        self._busy = False; self.refresh_button.set_sensitive(True); self.status.set_text(tr('Monitoring refresh failed: {v0}', v0=error))

    def _toggle_pause(self, _button: Gtk.Button) -> None:
        paused = not self._paused
        self._paused = paused
        self.pause_button.set_label(tr('Resume live refresh') if paused else tr('Pause live refresh'))
        self.live_label.set_text(tr('Live refresh: paused') if paused else tr('Live refresh: every 2 seconds'))

    @staticmethod
    def _format_bytes(value: int) -> str:
        amount = float(max(0, value)); units = ("B", "KB", "MB", "GB", "TB")
        for unit in units:
            if amount < 1024 or unit == units[-1]: return f"{amount:.1f} {unit}"
            amount /= 1024
        return f"{amount:.1f} TB"
