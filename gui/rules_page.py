"""GTK4 scheduled rule management workspace."""
from __future__ import annotations

from gi.repository import Gtk

from core.database import Database
from gui.tasks import BackgroundTaskRunner
from manager.rule_manager import RuleManager


class RulesPage(Gtk.Box):
    """Present policy rules and their schedules in the GTK4 UI."""

    def __init__(self, database: Database, tasks: BackgroundTaskRunner) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self.set_margin_top(28)
        self.set_margin_bottom(28)
        self.set_margin_start(32)
        self.set_margin_end(32)
        self.manager = RuleManager(database)
        self.tasks = tasks
        self._busy = False

        heading = Gtk.Label(label="Rules", xalign=0)
        heading.add_css_class("title-1")
        self.append(heading)
        subtitle = Gtk.Label(
            label="Review scheduled allow and block rules used by NetFather policies.",
            xalign=0,
            wrap=True,
        )
        subtitle.add_css_class("dim-label")
        self.append(subtitle)

        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.refresh_button = Gtk.Button(label="Refresh")
        self.refresh_button.add_css_class("suggested-action")
        self.refresh_button.connect("clicked", lambda _button: self.refresh())
        toolbar.append(self.refresh_button)
        self.append(toolbar)

        self.status = Gtk.Label(label="Ready", xalign=0)
        self.append(self.status)
        self.list_box = Gtk.ListBox()
        self.list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        self.list_box.set_vexpand(True)
        self.list_box.add_css_class("boxed-list")
        self.append(self.list_box)
        self.refresh()

    def refresh(self) -> None:
        if self._busy:
            return
        self._busy = True
        self.refresh_button.set_sensitive(False)
        self.status.set_text("Loading rules...")
        self.tasks.submit(self.manager.list_rules, self._loaded, self._failed)

    def _loaded(self, rules) -> None:
        self._busy = False
        self.refresh_button.set_sensitive(True)
        while (child := self.list_box.get_first_child()) is not None:
            self.list_box.remove(child)
        for rule in rules:
            row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            row.set_margin_top(12)
            row.set_margin_bottom(12)
            row.set_margin_start(14)
            row.set_margin_end(14)
            title = Gtk.Label(label=getattr(rule, "name", str(rule)), xalign=0)
            title.add_css_class("heading")
            row.append(title)
            mode = getattr(rule, "action", getattr(rule, "mode", "unknown"))
            schedule = getattr(rule, "schedule", getattr(rule, "time_range", ""))
            enabled = getattr(rule, "enabled", True)
            info = Gtk.Label(label=f"Action: {mode}  |  Schedule: {schedule}  |  {'Enabled' if enabled else 'Disabled'}", xalign=0, wrap=True)
            info.add_css_class("dim-label")
            row.append(info)
            self.list_box.append(row)
        self.status.set_text(f"{len(rules)} rules")

    def _failed(self, error: BaseException) -> None:
        self._busy = False
        self.refresh_button.set_sensitive(True)
        self.status.set_text(str(error))
