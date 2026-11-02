"""Full scheduled rule editing with explicit scope, precedence and timezone."""
from gi.repository import Gtk
from core.i18n import tr
from gui.base_page import BasePage
from gui.dialogs import field, confirm
from manager.device_manager import DeviceManager
from manager.group_manager import GroupManager
from manager.rule_manager import RuleManager
from manager.schedules import next_change, normalize_windows, normalize_days, zone

class RulesPage(BasePage):
    def __init__(self, database, tasks):
        super().__init__(tr("Rules"), tr("Block overrides allow. Priority selects a winner within the same action. Controlled profiles deny by default."))
        self.database, self.tasks = database, tasks
        self.manager = RuleManager(database); self._busy = False; self.selected = None
        self.target = Gtk.ComboBoxText()
        self.action = Gtk.ComboBoxText(); self.action.append("allow", tr("Allow")); self.action.append("block", tr("Block")); self.action.set_active_id("block")
        self.schedule = Gtk.Entry(text="22:00-07:00", placeholder_text="22:00-07:00;12:00-13:00")
        self.timezone = Gtk.Entry(text="local", placeholder_text="local / Europe/Istanbul / Asia/Baku")
        self.days = Gtk.Entry(text="0,1,2,3,4,5,6")
        self.priority = Gtk.SpinButton.new_with_range(0, 10000, 1)
        self.description = Gtk.Entry()
        self.enabled = Gtk.CheckButton(label=tr("Enabled")); self.enabled.set_active(True)
        for label, widget in ((tr("Scope"), self.target), (tr("Action"), self.action), (tr("Schedule windows"), self.schedule),
            (tr("Time zone"), self.timezone), (tr("Weekdays: 0 Monday — 6 Sunday"), self.days), (tr("Priority"), self.priority), (tr("Optional description"), self.description)):
            self.append(field(label, widget))
        self.append(self.enabled)
        self.preview = Gtk.Label(xalign=0, wrap=True); self.append(self.preview)
        for widget in (self.schedule, self.timezone, self.days): widget.connect("changed", lambda _: self._preview())
        self.action.connect("changed", lambda _: self._preview())
        self.save_button = Gtk.Button(label=tr("Save rule")); self.save_button.add_css_class("suggested-action"); self.save_button.connect("clicked", self._save); self.append(self.save_button)
        new = Gtk.Button(label=tr("New rule")); new.connect("clicked", lambda _: self._new()); self.append(new)
        self.status = Gtk.Label(xalign=0, wrap=True); self.append(self.status)
        self.list_box = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE); self.list_box.add_css_class("boxed-list"); self.list_box.connect("row-selected", self._selected); self.append(self.list_box)
        for label, callback in ((tr("Enable / disable"), self._toggle), (tr("Delete rule"), self._delete), (tr("Refresh"), lambda _: self.refresh())):
            button=Gtk.Button(label=label); button.connect("clicked",callback); self.append(button)
        self.refresh()

    def _load(self):
        return self.manager.all_rules(), DeviceManager(self.database).list_devices(), GroupManager(self.database).list_profiles(), self.manager.conflicts()

    def refresh(self):
        if self._busy: return
        self._busy=True; self.tasks.submit(self._load,self._loaded,self._failed)

    def _loaded(self, result):
        self._busy=False
        rules, devices, profiles, conflicts = result
        self.rules={(rule.group_rule,rule.id):rule for rule in rules}; self.devices={d.id:d for d in devices}
        self.target.remove_all()
        for device in devices: self.target.append(f"device:{device.id}", device.name)
        for profile in profiles: self.target.append(f"profile:{profile.id}", f"{tr('Profiles')}: {profile.name}")
        while (row:=self.list_box.get_first_child()) is not None:self.list_box.remove(row)
        for rule in rules:
            row=Gtk.ListBoxRow(); row.set_name(f"{int(rule.group_rule)}:{rule.id}")
            try:change=next_change(rule)
            except Exception:change=tr("Invalid schedule; review required")
            row.set_child(Gtk.Label(label=f"{rule.scope_label} | {tr(rule.action.title())} | {rule.schedule} | {rule.timezone} | {tr('Priority')}: {rule.priority} | {tr('Enabled')}: {rule.enabled} | {tr('Next transition')}: {change or tr('None')}",xalign=0,wrap=True))
            self.list_box.append(row)
        self.status.set_text("\n".join(conflicts) or tr("Ready"))
        self._preview()

    def _selected(self,_list,row):
        self.selected=None if not row else tuple(int(part) for part in row.get_name().split(":"))
        if not row:return
        rule=self.rules[self.selected]
        self.target.set_active_id(f"profile:{rule.profile_id}" if rule.group_rule else f"device:{rule.device_id}")
        self.target.set_sensitive(False)
        self.action.set_active_id(rule.action); self.schedule.set_text(rule.schedule); self.timezone.set_text(rule.timezone); self.days.set_text(rule.weekdays)
        self.priority.set_value(rule.priority); self.description.set_text(rule.description or ""); self.enabled.set_active(rule.enabled)

    def _new(self):
        self.list_box.unselect_all(); self.selected=None; self.target.set_sensitive(True)
        self.schedule.set_text("22:00-07:00"); self.timezone.set_text("local"); self.days.set_text("0,1,2,3,4,5,6"); self.enabled.set_active(True)

    def _preview(self):
        try:
            normalized=normalize_windows(self.schedule.get_text()); days=normalize_days(self.days.get_text()); zone(self.timezone.get_text())
            text=f"{self.action.get_active_id() or 'block'} | {normalized} | {self.timezone.get_text()} | {days}"
            self.preview.set_text(text + "\n" + tr("Rules affect the whole device. Service/port and destination selectors are unavailable in the current backend."))
        except Exception as exc:self.preview.set_text(str(exc))

    def _save(self,_button):
        options=dict(action=self.action.get_active_id(),schedule=self.schedule.get_text(), enabled=self.enabled.get_active(),description=self.description.get_text(),
            priority=int(self.priority.get_value()),timezone=self.timezone.get_text().strip(),weekdays=self.days.get_text())
        if self.selected:
            group,identifier=self.selected
            work=lambda:self.manager.update_rule(identifier,group=bool(group),**options)
        else:
            target=self.target.get_active_id()
            if not target:return
            kind,identifier=target.split(":")
            name=self.devices[int(identifier)].name if kind=="device" else None
            work=lambda:self.manager.create_rule(name,profile_id=int(identifier) if kind=="profile" else None,**options)
        confirm(self.get_root(),tr("Save rule"),self.preview.get_text(),tr("Confirm"),lambda:self._mutate(work))

    def _toggle(self,_button):
        if self.selected:
            group,identifier=self.selected; rule=self.rules[self.selected]
            confirm(self.get_root(),tr("Enable / disable"),tr("Change the selected rule state?"),tr("Confirm"),
                lambda:self._mutate(lambda:self.manager.set_enabled(identifier,not rule.enabled,group=bool(group))))

    def _delete(self,_button):
        if self.selected:
            group,identifier=self.selected
            confirm(self.get_root(),tr("Delete rule"),tr("Permanently remove the selected rule?"),tr("Delete rule"),
                lambda:self._mutate(lambda:self.manager.delete_rule(identifier,group=bool(group))))

    def _mutate(self,work):
        if self._busy:return
        self._busy=True;self.save_button.set_sensitive(False);self.tasks.submit(work,self._saved,self._failed)

    def _saved(self,_result):
        self._busy=False;self.save_button.set_sensitive(True);self.selected=None;self.target.set_sensitive(True);self.refresh()

    def _failed(self,error):
        self._busy=False;self.save_button.set_sensitive(True);self.status.set_text(tr("Operation failed: {error}",error=error))
