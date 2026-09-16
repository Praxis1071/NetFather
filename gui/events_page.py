"""GTK4 event and audit history workspace."""
from __future__ import annotations

from gi.repository import Gtk
from sqlalchemy import select

from core.database import Database
from gui.tasks import BackgroundTaskRunner
from models.event import Event


class EventsPage(Gtk.Box):
    def __init__(self, database: Database, tasks: BackgroundTaskRunner) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self.set_margin_top(28); self.set_margin_bottom(28); self.set_margin_start(32); self.set_margin_end(32)
        self.database = database; self.tasks = tasks; self._busy = False
        title = Gtk.Label(label="Events", xalign=0); title.add_css_class("title-1"); self.append(title)
        subtitle = Gtk.Label(label="Recent device, discovery and policy events recorded by NetFather.", xalign=0, wrap=True); subtitle.add_css_class("dim-label"); self.append(subtitle)
        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.refresh_button = Gtk.Button(label="Refresh"); self.refresh_button.add_css_class("suggested-action"); self.refresh_button.connect("clicked", lambda _b: self.refresh()); toolbar.append(self.refresh_button)
        self.count = Gtk.Label(label="", xalign=0); self.count.add_css_class("dim-label"); toolbar.append(self.count); self.append(toolbar)
        self.list_box = Gtk.ListBox(); self.list_box.set_selection_mode(Gtk.SelectionMode.NONE); self.list_box.add_css_class("boxed-list"); self.list_box.set_vexpand(True); self.append(self.list_box)
        self.empty = Gtk.Label(label="No events recorded yet.", xalign=0); self.empty.add_css_class("dim-label")
        self.refresh()

    def refresh(self) -> None:
        if self._busy: return
        self._busy = True; self.refresh_button.set_sensitive(False); self.tasks.submit(self._load, self._loaded, self._failed)

    def _load(self) -> list[Event]:
        with self.database.session() as session:
            events = list(session.scalars(select(Event).order_by(Event.timestamp.desc()).limit(100)).all())
            for event in events: session.expunge(event)
            return events

    def _loaded(self, events: list[Event]) -> None:
        self._busy = False; self.refresh_button.set_sensitive(True); self.count.set_text(f"{len(events)} recent event(s)")
        while (child := self.list_box.get_first_child()) is not None: self.list_box.remove(child)
        if not events: self.list_box.append(self.empty); return
        for event in events:
            row = Gtk.ListBoxRow(); box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3); box.set_margin_top(10); box.set_margin_bottom(10); box.set_margin_start(12); box.set_margin_end(12)
            heading = Gtk.Label(label=f"{event.event_type}  ·  {event.severity.upper()}", xalign=0); heading.add_css_class("heading"); box.append(heading)
            timestamp = event.timestamp.astimezone().strftime("%Y-%m-%d %H:%M:%S") if event.timestamp else "Unknown time"
            detail = Gtk.Label(label=f"{timestamp}  ·  {event.description}", xalign=0, wrap=True); detail.add_css_class("dim-label"); box.append(detail)
            if event.device_mac:
                device = Gtk.Label(label=f"Device: {event.device_mac}", xalign=0); device.add_css_class("caption"); box.append(device)
            row.set_child(box); self.list_box.append(row)

    def _failed(self, error: BaseException) -> None:
        self._busy = False; self.refresh_button.set_sensitive(True); self.count.set_text("Refresh failed")
        while (child := self.list_box.get_first_child()) is not None: self.list_box.remove(child)
        label = Gtk.Label(label=f"Unable to load events: {error}", xalign=0, wrap=True); label.add_css_class("error"); self.list_box.append(label)
