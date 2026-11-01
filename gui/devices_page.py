"""Native device inventory, evidence details and explicit identity review."""
from __future__ import annotations

import json
from gi.repository import Gtk
from core.i18n import tr
from gui.base_page import BasePage
from gui.dialogs import confirm, field
from manager.device_service import DeviceService
from manager.identity_manager import IdentityManager

class DevicesPage(BasePage):
    def __init__(self, database, state, tasks):
        super().__init__(tr("Devices"), tr("Manage registered devices and inspect their current network identity."))
        self.database, self.state, self.tasks = database, state, tasks
        self.service = DeviceService(database)
        self.selected_name = None
        self._busy = False
        self._closed = False
        self._unsubscribe = state.subscribe(self._on_state_changed)
        self.refresh_button = Gtk.Button(label=tr("Refresh"))
        self.refresh_button.connect("clicked", lambda _: self.refresh())
        self.append(self.refresh_button)
        self.count_label = Gtk.Label(xalign=0, wrap=True)
        self.append(self.count_label)
        self.list_box = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.list_box.add_css_class("boxed-list")
        self.list_box.connect("row-selected", self._selected)
        self.append(self.list_box)
        self.detail = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.detail_title = Gtk.Label(label=tr("Select a device"), xalign=0)
        self.detail_title.add_css_class("title-2")
        self.detail.append(self.detail_title)
        self.evidence = Gtk.Label(xalign=0, wrap=True, selectable=True)
        self.detail.append(self.evidence)
        self.name_entry, self.ip_entry, self.vendor_entry, self.type_entry = (Gtk.Entry() for _ in range(4))
        for label, widget in ((tr("Name"), self.name_entry), (tr("IP address"), self.ip_entry),
                              (tr("Vendor"), self.vendor_entry), (tr("Device type"), self.type_entry)):
            self.detail.append(field(label, widget))
        self.save_button = Gtk.Button(label=tr("Save changes"))
        self.save_button.add_css_class("suggested-action")
        self.save_button.connect("clicked", self._save)
        self.detail.append(self.save_button)
        self.review_reason = Gtk.Entry(placeholder_text=tr("Review reason"))
        self.detail.append(field(tr("Identity review"), self.review_reason))
        self.resolve = Gtk.Button(label=tr("Resolve identity conflict"))
        self.resolve.connect("clicked", self._resolve)
        self.detail.append(self.resolve)
        self.link_target = Gtk.ComboBoxText()
        self.detail.append(field(tr("Link another identity"), self.link_target))
        self.link_button = Gtk.Button(label=tr("Link identity"))
        self.link_button.connect("clicked", self._link)
        self.detail.append(self.link_button)
        self.alias = Gtk.ComboBoxText()
        self.detail.append(field(tr("Linked MAC addresses"), self.alias))
        self.split_name = Gtk.Entry(placeholder_text=tr("Device name"))
        self.detail.append(field(tr("Name for split device"), self.split_name))
        self.split_button = Gtk.Button(label=tr("Split identity"))
        self.split_button.connect("clicked", self._split)
        self.detail.append(self.split_button)
        self.delete_button = Gtk.Button(label=tr("Delete device"))
        self.delete_button.add_css_class("destructive-action")
        self.delete_button.connect("clicked", self._delete)
        self.detail.append(self.delete_button)
        self.detail.set_visible(False)
        self.append(self.detail)
        self.message = Gtk.Label(xalign=0, wrap=True)
        self.append(self.message)
        self.refresh()

    def cleanup(self):
        self._closed = True
        self._unsubscribe()

    def refresh(self):
        if self._busy or self._closed:
            return
        self._busy = True
        name = self.selected_name
        self.refresh_button.set_sensitive(False)
        self.tasks.submit(lambda: self.service.refresh(name), self._loaded, self._failed)

    def _loaded(self, snapshot):
        self._busy = False
        self.refresh_button.set_sensitive(True)
        self.count_label.set_text(tr("{v0} registered", v0=len(snapshot.devices)))
        self._devices = {device.name: device for device in snapshot.devices}
        selected = snapshot.selected_name
        while (child := self.list_box.get_first_child()) is not None:
            self.list_box.remove(child)
        selected_row = None
        for device in snapshot.devices:
            row = Gtk.ListBoxRow()
            row.set_name(device.name)
            label = Gtk.Label(label=f"{device.name}  |  {device.ip or tr('No IP')}  |  {tr('Online') if device.online else tr('Offline')}" +
                              ("  |  " + tr("Identity conflict") if device.identity_conflict else ""), xalign=0, wrap=True)
            label.set_margin_top(10); label.set_margin_bottom(10); label.set_margin_start(12); label.set_margin_end(12)
            row.set_child(label)
            self.list_box.append(row)
            if device.name == selected:
                selected_row = row
        self.list_box.select_row(selected_row)
        if not snapshot.devices:
            self.message.set_text(tr("No devices discovered yet."))

    def _selected(self, _list, row):
        self.selected_name = row.get_name() if row else None
        self.detail.set_visible(bool(row))
        if row:
            self.detail.set_sensitive(False)
            name = self.selected_name
            self.evidence.set_text(tr("Loading devices..."))
            self.tasks.submit(lambda: self.service.details(name),
                lambda result: self._details(result) if name == self.selected_name else None, self._failed)

    def _details(self, result):
        self.detail.set_sensitive(True)
        self._result = result
        device = result["device"]
        self.detail_title.set_text(device.name)
        for widget, value in ((self.name_entry, device.name), (self.ip_entry, device.ip),
                              (self.vendor_entry, device.vendor), (self.type_entry, device.device_type)):
            widget.set_text(value or "")
        observations = result["observations"]
        sources = ", ".join(sorted({item.source for item in observations})) or tr("Unknown")
        confidence = max((item.confidence for item in observations), default=0)
        addresses = "\n".join(f"{item.ip} [{item.interface or tr('Unknown interface')}] — {item.last_seen} UTC" for item in result["addresses"])
        profiles = ", ".join(f"{item.name}: {item.internet_mode}" for item in result["profiles"]) or tr("None")
        services = "\n".join(f"{item.observed_at} UTC  {item.ip}  TCP {item.tcp_ports}  UDP {item.udp_ports}  {item.services}" for item in result["services"])
        events = "\n".join(f"{item.timestamp} UTC  {item.event_type}: {item.description}" for item in result["events"])
        policy = result["policy"]
        self.evidence.set_text(
            f"MAC: {device.mac}\n{tr('Hostname')}: {device.hostname or tr('Unknown')}\n"
            f"{tr('Identity confidence')}: {confidence:.0%} | {sources}\n{device.identity_note or ''}\n"
            f"{tr('Profiles')}: {profiles}\n{tr('Desired policy')}: {policy.reason}\n"
            f"{tr('Enforcement state')}: {result['enforcement']}\n\n{tr('Address history')}\n{addresses or tr('None')}\n\n"
            f"{tr('Discovered services')}\n{services or tr('None')}\n\n{tr('Events')}\n{events or tr('None')}")
        self.resolve.set_sensitive(device.identity_conflict)
        self.link_target.remove_all()
        for other in self._devices.values():
            if other.id != device.id:
                self.link_target.append(str(other.id), f"{other.name} — {other.mac}")
        self.alias.remove_all()
        for item in result["aliases"]:
            self.alias.append(item.mac, item.mac)
        self.split_button.set_sensitive(bool(result["aliases"]))

    def _mutate(self, work):
        if self._busy:
            return
        self._busy = True
        self.detail.set_sensitive(False)
        self.tasks.submit(work, self._saved, self._failed)

    def _saved(self, _result):
        self._busy = False
        self.detail.set_sensitive(True)
        self.message.set_text(tr("Device changes saved."))
        self.refresh()

    def _save(self, _button):
        if not self.selected_name:
            return
        name, new_name = self.selected_name, self.name_entry.get_text().strip()
        ip, vendor, kind = self.ip_entry.get_text().strip(), self.vendor_entry.get_text().strip(), self.type_entry.get_text().strip()
        def save():
            self.service.update(name, new_name=new_name, ip=ip, vendor=vendor, device_type=kind or "unknown")
        self.selected_name = new_name
        self._mutate(save)

    def _delete(self, _button):
        if not self.selected_name or self._busy:
            return
        device = self._devices[self.selected_name]
        confirm(self.get_root(), tr("Delete device"), tr("Remove this device and its attached policies and history?"),
                tr("Delete device"), lambda: self._mutate(lambda: self.service.manager.delete_device(device.name, expected_id=device.id)))

    def _resolve(self, _button):
        device, reason = self._result["device"], self.review_reason.get_text().strip()
        confirm(self.get_root(), tr("Resolve identity conflict"), tr("Verify the physical device and address before continuing."),
            tr("Confirm"), lambda: self._mutate(lambda: IdentityManager(self.database).resolve_conflict(
                device.id, expected_ip=device.ip, expected_mac=device.mac, reason=reason)))

    def _link(self, _button):
        target = self.link_target.get_active_id()
        if not target:
            return
        device, reason = self._result["device"], self.review_reason.get_text().strip()
        candidate = next(item for item in self._devices.values() if item.id == int(target))
        confirm(self.get_root(), tr("Link identity"), tr("Link only after verifying these are the same physical device. Policies are not copied."),
            tr("Confirm"), lambda: self._mutate(lambda: IdentityManager(self.database).merge(device.id, candidate.id,
                expected_macs=(device.mac, candidate.mac), reason=reason, confirmed=True)))

    def _split(self, _button):
        alias, name = self.alias.get_active_id(), self.split_name.get_text().strip()
        if not alias:
            return
        device = self._result["device"]
        confirm(self.get_root(), tr("Split identity"), tr("Create a separate offline device without copying policies?"),
            tr("Confirm"), lambda: self._mutate(lambda: IdentityManager(self.database).split(device.id, alias, name=name, confirmed=True)))

    def _failed(self, error):
        self._busy = False
        self.detail.set_sensitive(True)
        self.refresh_button.set_sensitive(True)
        self.message.set_text(tr("Operation failed: {error}", error=error))

    def _on_state_changed(self):
        if not self.state.discovery.running:
            self.refresh()
