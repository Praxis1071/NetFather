"""GTK4 scheduled rule management workspace."""
from __future__ import annotations

from core.i18n import tr

from gi.repository import Gtk

from core.database import Database
from gui.tasks import BackgroundTaskRunner
from manager.device_manager import DeviceManager
from manager.rule_manager import RuleManager


ACTIONS = ("allow", "block")


class RulesPage(Gtk.Box):
    """Create and review device-bound scheduled rules through GTK4."""

    def __init__(self, database: Database, tasks: BackgroundTaskRunner) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self.set_margin_top(28)
        self.set_margin_bottom(28)
        self.set_margin_start(32)
        self.set_margin_end(32)
        self.rule_manager = RuleManager(database)
        self.device_manager = DeviceManager(database)
        self.tasks = tasks
        self._busy = False
        self._device_names: list[str] = []

        heading = Gtk.Label(label=tr('Rules'), xalign=0)
        heading.add_css_class("title-1")
        self.append(heading)
        subtitle = Gtk.Label(
            label=tr('Define scheduled allow or block windows for managed devices.'),
            xalign=0,
            wrap=True,
        )
        subtitle.add_css_class("dim-label")
        self.append(subtitle)

        form = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.device = Gtk.DropDown.new_from_strings([tr('Loading devices...')])
        self.device.set_hexpand(True)
        self.action = Gtk.DropDown.new_from_strings([tr(action.title()) for action in ACTIONS])
        self.schedule = Gtk.Entry(placeholder_text="HH:MM-HH:MM")
        self.schedule.set_text("22:00-07:00")
        self.schedule.set_hexpand(True)
        self.description = Gtk.Entry(placeholder_text=tr('Optional description'))
        self.description.set_hexpand(True)
        self.create_button = Gtk.Button(label=tr('Create rule'))
        self.create_button.add_css_class("suggested-action")
        self.create_button.connect("clicked", lambda _button: self.create_rule())
        form.append(self.device)
        form.append(self.action)
        form.append(self.schedule)
        form.append(self.description)
        form.append(self.create_button)
        self.append(form)

        self.refresh_button = Gtk.Button(label=tr('Refresh'))
        self.refresh_button.connect("clicked", lambda _button: self.refresh())
        self.append(self.refresh_button)
        self.status = Gtk.Label(label=tr('Ready'), xalign=0, wrap=True)
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
        self.create_button.set_sensitive(False)
        self.status.set_text(tr('Loading rules and devices...'))
        self.tasks.submit(self._load, self._loaded, self._failed)

    def _load(self):
        return self.rule_manager.list_rules(), self.device_manager.list_devices()

    def _loaded(self, result) -> None:
        rules, devices = result
        self._busy = False
        self.refresh_button.set_sensitive(True)
        self.create_button.set_sensitive(True)
        self._device_names = [device.name for device in devices]
        values = self._device_names or [tr('No devices')]
        self.device.set_model(Gtk.StringList.new(values))
        self.device.set_selected(0)
        while (child := self.list_box.get_first_child()) is not None:
            self.list_box.remove(child)
        for rule in rules:
            row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            row.set_margin_top(12)
            row.set_margin_bottom(12)
            row.set_margin_start(14)
            row.set_margin_end(14)
            device = getattr(rule, "device", None)
            device_name = device.name if device is not None else tr('Unknown device')
            title = Gtk.Label(label=f"{device_name}  —  {tr(rule.action.title())}", xalign=0)
            title.add_css_class("heading")
            row.append(title)
            enabled = tr('Enabled') if rule.enabled else tr('Disabled')
            details = Gtk.Label(
                label=tr('Schedule: {v0}  |  {v1}  |  {v2}', v0=rule.schedule, v1=enabled, v2=rule.description or tr('No description')),
                xalign=0,
                wrap=True,
            )
            details.add_css_class("dim-label")
            row.append(details)
            self.list_box.append(row)
        self.status.set_text(tr('{v0} rules | {v1} devices', v0=len(rules), v1=len(devices)))

    def create_rule(self) -> None:
        selected = self.device.get_selected_item()
        device_name = selected.get_string() if selected else ""
        schedule = self.schedule.get_text().strip()
        if not self._device_names or not device_name:
            self.status.set_text(tr('Select a device first.'))
            return
        if not schedule:
            self.status.set_text(tr('Enter a schedule such as 22:00-07:00.'))
            return
        action = ACTIONS[self.action.get_selected()]
        description = self.description.get_text().strip() or None
        if self._busy:
            return
        self._busy = True
        self.create_button.set_sensitive(False)
        self.refresh_button.set_sensitive(False)
        self.status.set_text(tr('Creating rule...'))
        self.tasks.submit(
            lambda: self.rule_manager.create_rule(device_name, action, schedule, description=description),
            self._created,
            self._failed,
        )

    def _created(self, _rule) -> None:
        self._busy = False
        self.description.set_text("")
        self.create_button.set_sensitive(True)
        self.refresh_button.set_sensitive(True)
        self.status.set_text(tr('Rule created.'))
        self.refresh()

    def _failed(self, error: BaseException) -> None:
        self._busy = False
        self.refresh_button.set_sensitive(True)
        self.create_button.set_sensitive(True)
        self.status.set_text(tr("Operation failed: {error}", error=error))
