"""Reusable profiles, explicit assignments and policy history."""
from gi.repository import Gtk
from core.i18n import tr
from gui.base_page import BasePage
from gui.dialogs import field, confirm
from manager.group_manager import GroupManager
from manager.profile_manager import ProfileManager
from manager.device_manager import DeviceManager
from manager.policy_engine import PolicyEngine

MODES = ("unrestricted", "controlled", "blocked")

class ProfilesPage(BasePage):
    def __init__(self, database, tasks):
        super().__init__(tr("Profiles"), tr("Reusable access profiles. Assign devices explicitly and inspect their effective policy."))
        self.database, self.tasks = database, tasks
        self.manager, self.legacy = GroupManager(database), ProfileManager(database)
        self.selected_id = None
        self._busy = False
        self.name_entry = Gtk.Entry()
        self.mode = Gtk.ComboBoxText()
        for mode in MODES:
            self.mode.append(mode, tr(mode.title()))
        self.mode.set_active_id("controlled")
        self.append(field(tr("Profile name"), self.name_entry))
        self.append(field(tr("Mode"), self.mode))
        self.save_button = Gtk.Button(label=tr("Save profile"))
        self.save_button.add_css_class("suggested-action")
        self.save_button.connect("clicked", self._save)
        self.append(self.save_button)
        new = Gtk.Button(label=tr("New profile")); new.connect("clicked", lambda _: self._new()); self.append(new)
        self.list_box = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.list_box.add_css_class("boxed-list"); self.list_box.connect("row-selected", self._selected); self.append(self.list_box)
        self.device = Gtk.ComboBoxText()
        self.append(field(tr("Devices"), self.device))
        for label, callback in ((tr("Assign device"), self._assign), (tr("Unassign device"), self._unassign), (tr("Delete profile"), self._delete)):
            button = Gtk.Button(label=label); button.connect("clicked", callback); self.append(button)
        self.details = Gtk.Label(xalign=0, wrap=True, selectable=True); self.append(self.details)
        self.legacy_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        expander = Gtk.Expander(label=tr("Existing device-bound profiles")); expander.set_child(self.legacy_box); self.append(expander)
        self.status = Gtk.Label(xalign=0, wrap=True); self.append(self.status)
        self.refresh_button = Gtk.Button(label=tr("Refresh")); self.refresh_button.connect("clicked", lambda _: self.refresh()); self.append(self.refresh_button)
        self.refresh()

    def _load(self):
        profiles = self.manager.list_profiles()
        assignments = {p.id: self.manager.assignments(p.id) for p in profiles}
        histories = {p.id: self.manager.history(p.id) for p in profiles}
        return profiles, assignments, histories, DeviceManager(self.database).list_devices(), PolicyEngine(self.database).evaluate_all(), self.legacy.list_profiles()

    def refresh(self):
        if self._busy: return
        self._busy = True; self.status.set_text(tr("Loading profiles and devices..."))
        self.tasks.submit(self._load, self._loaded, self._failed)

    def _loaded(self, result):
        self._busy = False
        profiles, self.assignments, self.histories, devices, policies, legacy = result
        self.profiles = {p.id: p for p in profiles}; self.policies = {p.device_id: p for p in policies}
        selected = self.selected_id
        while (row := self.list_box.get_first_child()) is not None: self.list_box.remove(row)
        self.device.remove_all()
        for device in devices: self.device.append(str(device.id), device.name)
        selected_row = None
        for profile in profiles:
            row = Gtk.ListBoxRow(); row.set_name(str(profile.id))
            row.set_child(Gtk.Label(label=f"{profile.name} | {tr(profile.internet_mode.title())} | {len(self.assignments[profile.id])}", xalign=0, wrap=True))
            self.list_box.append(row)
            if profile.id == selected: selected_row = row
        self.list_box.select_row(selected_row)
        while (child := self.legacy_box.get_first_child()) is not None: self.legacy_box.remove(child)
        for profile in legacy:
            self._legacy_row(profile)
        self.status.set_text(tr("{v0} profiles | {v1} devices", v0=len(profiles), v1=len(devices)))

    def _legacy_row(self, profile):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.append(Gtk.Label(label=f"{profile.device.name}: {profile.name}", xalign=0, wrap=True))
        name = Gtk.Entry(text=profile.name)
        mode = Gtk.ComboBoxText()
        for value in MODES: mode.append(value, tr(value.title()))
        mode.set_active_id(profile.internet_mode)
        box.append(field(tr("Name"), name)); box.append(field(tr("Mode"), mode))
        def save(_button):
            text, value = name.get_text(), mode.get_active_id()
            self._mutate(lambda: self.legacy.update_profile(profile.id, name=text, internet_mode=value))
        button = Gtk.Button(label=tr("Save changes")); button.connect("clicked", save); box.append(button)
        button = Gtk.Button(label=tr("Delete profile"))
        button.connect("clicked", lambda _: confirm(self.get_root(), tr("Delete profile"), tr("Remove this device-bound policy?"), tr("Delete profile"),
            lambda: self._mutate(lambda: self.legacy.delete_profile(profile.id))))
        box.append(button); self.legacy_box.append(box)

    def _selected(self, _list, row):
        self.selected_id = int(row.get_name()) if row else None
        if not row: return
        profile = self.profiles[self.selected_id]
        self.name_entry.set_text(profile.name); self.mode.set_active_id(profile.internet_mode)
        lines = []
        for device in self.assignments[profile.id]:
            policy = self.policies.get(device.id)
            if policy:
                lines.append(f"{device.name}: {policy.reason} | {tr('Next transition')}: {policy.next_transition or tr('None')}")
        lines.extend(f"{event.timestamp} UTC | {event.description}" for event in self.histories[profile.id])
        self.details.set_text("\n".join(lines) or tr("No devices"))

    def _new(self):
        self.list_box.unselect_all(); self.selected_id = None; self.name_entry.set_text(""); self.mode.set_active_id("controlled")

    def _save(self, _button):
        name, mode, selected = self.name_entry.get_text(), self.mode.get_active_id(), self.selected_id
        work = lambda: self.manager.save(name, mode, profile_id=selected)
        if selected and self.assignments.get(selected):
            confirm(self.get_root(), tr("Save profile"), tr("Apply this profile change to every assigned device?"), tr("Confirm"), lambda: self._mutate(work))
        else: self._mutate(work)

    def _assign(self, _button):
        selected, device = self.selected_id, self.device.get_active_id()
        if selected and device:
            confirm(self.get_root(), tr("Assign device"), tr("Apply this profile to the selected device?"), tr("Confirm"),
                lambda: self._mutate(lambda: self.manager.assign(selected, int(device))))

    def _unassign(self, _button):
        selected, device = self.selected_id, self.device.get_active_id()
        if selected and device:
            confirm(self.get_root(), tr("Unassign device"), tr("Remove the selected profile assignment?"), tr("Confirm"),
                lambda: self._mutate(lambda: self.manager.unassign(selected, int(device))))

    def _delete(self, _button):
        selected = self.selected_id
        if selected:
            confirm(self.get_root(), tr("Delete profile"), tr("All devices must be unassigned before deleting a reusable profile."), tr("Delete profile"),
                lambda: self._mutate(lambda: self.manager.delete(selected)))

    def _mutate(self, work):
        if self._busy: return
        self._busy = True; self.save_button.set_sensitive(False)
        self.tasks.submit(work, self._saved, self._failed)

    def _saved(self, _result):
        self._busy = False; self.save_button.set_sensitive(True); self.refresh()

    def _failed(self, error):
        self._busy = False; self.save_button.set_sensitive(True); self.status.set_text(tr("Operation failed: {error}", error=error))
