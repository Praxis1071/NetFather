"""Device management GTK page."""
from __future__ import annotations

from datetime import datetime
from gi.repository import Gtk
from core.database import Database
from gui.base_page import BasePage
from gui.state import ApplicationState
from gui.tasks import BackgroundTaskRunner
from manager.device_service import DeviceService, DeviceSnapshot
from models.device import Device

class DevicesPage(BasePage):
    def __init__(self,database:Database,state:ApplicationState,tasks:BackgroundTaskRunner)->None:
        super().__init__("Devices","Manage registered devices and inspect their current network identity."); self.state=state; self.tasks=tasks; self.service=DeviceService(database); self.selected_name=None; self._busy=False; self._confirm_delete=False; self._unsubscribe=state.subscribe(self._on_state_changed)
        toolbar=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=10); self.refresh_button=Gtk.Button(label="Refresh"); self.refresh_button.connect("clicked",lambda _b:self.refresh()); toolbar.append(self.refresh_button); self.count_label=Gtk.Label(xalign=0); self.count_label.add_css_class("dim-label"); toolbar.append(self.count_label); self.append(toolbar); content=Gtk.Paned.new(Gtk.Orientation.HORIZONTAL); content.set_wide_handle(True); content.set_vexpand(True); self.append(content); self.list_box=Gtk.ListBox(); self.list_box.set_selection_mode(Gtk.SelectionMode.SINGLE); self.list_box.add_css_class("boxed-list"); self.list_box.set_vexpand(True); self.list_box.connect("row-selected",self._on_row_selected); content.set_start_child(self.list_box)
        detail=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12); detail.set_margin_start(24); detail.set_margin_end(8); detail.set_vexpand(True); content.set_end_child(detail); self.detail_title=Gtk.Label(label="Select a device",xalign=0); self.detail_title.add_css_class("title-2"); detail.append(self.detail_title); self.detail_status=Gtk.Label(xalign=0,wrap=True); self.detail_status.add_css_class("dim-label"); detail.append(self.detail_status); self.name_entry=Gtk.Entry(); self.ip_entry=Gtk.Entry(); self.vendor_entry=Gtk.Entry(); self.type_entry=Gtk.Entry(); self.name_entry.set_placeholder_text("Device name"); self.ip_entry.set_placeholder_text("Current IP"); self.vendor_entry.set_placeholder_text("Vendor"); self.type_entry.set_placeholder_text("unknown")
        for label,entry in (("Name",self.name_entry),("IP address",self.ip_entry),("Vendor",self.vendor_entry),("Device type",self.type_entry)):detail.append(self._field(label,entry))
        self.save_button=Gtk.Button(label="Save changes"); self.save_button.add_css_class("suggested-action"); self.save_button.connect("clicked",self._save); detail.append(self.save_button); self.delete_button=Gtk.Button(label="Delete device"); self.delete_button.add_css_class("destructive-action"); self.delete_button.connect("clicked",self._delete); detail.append(self.delete_button); self.message=Gtk.Label(xalign=0,wrap=True); detail.append(self.message); self._set_detail(None); self.refresh()
    @staticmethod
    def _field(label:str,widget:Gtk.Widget)->Gtk.Box:
        box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=4); heading=Gtk.Label(label=label,xalign=0); heading.add_css_class("caption-heading"); box.append(heading); box.append(widget); return box
    def refresh(self)->None:
        if self._busy:return
        self._busy=True; self.refresh_button.set_sensitive(False); self.tasks.submit(lambda:self.service.refresh(self.selected_name),self._refresh_finished,self._operation_failed)
    def _refresh_finished(self,snapshot:DeviceSnapshot)->None:
        self._busy=False; self.refresh_button.set_sensitive(True); self._render(snapshot.devices); selected=next((d for d in snapshot.devices if d.name==snapshot.selected_name),None); self.selected_name=selected.name if selected else None; self._set_detail(selected); self.count_label.set_text(f"{len(snapshot.devices)} registered")
    def _render(self,devices:tuple[Device,...])->None:
        while (child:=self.list_box.get_first_child()) is not None:self.list_box.remove(child)
        for device in devices:
            row=Gtk.ListBoxRow(); row.set_name(device.name); box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=3); box.set_margin_top(10); box.set_margin_bottom(10); box.set_margin_start(12); box.set_margin_end(12); name=Gtk.Label(label=device.name,xalign=0); name.add_css_class("heading"); box.append(name); meta=Gtk.Label(label=f"{'Online' if device.online else 'Offline'}  |  {device.ip or 'No IP'}  |  {device.mac}",xalign=0); meta.add_css_class("dim-label"); box.append(meta); row.set_child(box); self.list_box.append(row)
    def _on_row_selected(self,_list,row)->None:
        self._confirm_delete=False; self.selected_name=row.get_name() if row else None; self._set_detail(next((d for d in self.service.snapshot.devices if d.name==self.selected_name),None))
    def _set_detail(self,device:Device|None)->None:
        enabled=device is not None and not self._busy
        for entry in (self.name_entry,self.ip_entry,self.vendor_entry,self.type_entry):entry.set_sensitive(enabled)
        self.save_button.set_sensitive(enabled); self.delete_button.set_sensitive(enabled); self.message.set_text("") if device is None else None
        if device is None:self.detail_title.set_text("Select a device"); self.detail_status.set_text("Choose a device from the list to inspect and edit it."); [e.set_text("") for e in (self.name_entry,self.ip_entry,self.vendor_entry,self.type_entry)]; return
        self.detail_title.set_text(device.name); last=self._format_time(device.last_seen); self.detail_status.set_text(f"MAC: {device.mac}\nHostname: {device.hostname or 'Unknown'}\nOS hint: {device.os_hint or 'Unknown'}\nStatus: {'Online' if device.online else 'Offline'}\nLast seen: {last}\nRegistration: {'Automatic discovery' if device.auto_registered else 'Manual'}"); self.name_entry.set_text(device.name); self.ip_entry.set_text(device.ip or ""); self.vendor_entry.set_text(device.vendor or ""); self.type_entry.set_text(device.device_type or "unknown")
    @staticmethod
    def _format_time(value:datetime|None)->str:return "Never" if value is None else value.astimezone().strftime("%Y-%m-%d %H:%M:%S")
    def _save(self,_button)->None:
        if not self.selected_name or self._busy:return
        current=self.selected_name; new_name=self.name_entry.get_text().strip(); ip=self.ip_entry.get_text().strip() or None; vendor=self.vendor_entry.get_text().strip() or None; dtype=self.type_entry.get_text().strip() or "unknown"
        if not new_name:self.message.set_text("Device name cannot be empty."); return
        self._busy=True; self._set_detail(next((d for d in self.service.snapshot.devices if d.name==current),None)); self.tasks.submit(lambda:self.service.update(current,new_name=new_name,ip=ip,vendor=vendor,device_type=dtype),self._save_finished,self._operation_failed)
    def _save_finished(self,snapshot:DeviceSnapshot)->None:self.selected_name=snapshot.selected_name; self._refresh_finished(snapshot); self.message.set_text("Device changes saved.")
    def _delete(self,_button)->None:
        if not self.selected_name or self._busy:return
        if not self._confirm_delete:self._confirm_delete=True; self.message.set_text("Click Delete device again to permanently remove this device."); return
        name=self.selected_name; self._busy=True; self._set_detail(next((d for d in self.service.snapshot.devices if d.name==name),None)); self.tasks.submit(lambda:self.service.delete(name),self._delete_finished,self._operation_failed)
    def _delete_finished(self,snapshot:DeviceSnapshot)->None:self._busy=False; self._confirm_delete=False; self.selected_name=None; self._refresh_finished(snapshot); self.message.set_text("Device deleted.")
    def _operation_failed(self,error:BaseException)->None:self._busy=False; self.refresh_button.set_sensitive(True); self._set_detail(next((d for d in self.service.snapshot.devices if d.name==self.selected_name),None)); self.message.set_text(str(error)); self.message.add_css_class("error")
    def _on_state_changed(self)->None:
        if not self.state.discovery.running:self.refresh()

