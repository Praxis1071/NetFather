"""GTK4 pages for the Linux application."""
from __future__ import annotations

from datetime import datetime
from gi.repository import GLib, Gtk
from sqlalchemy import func, select
from core.config import Config
from core.database import Database
from gui.state import ApplicationState
from gui.tasks import BackgroundTaskRunner
from manager.device_manager import DeviceManager
from manager.device_service import DeviceService, DeviceSnapshot
from models.device import Device
from network.discovery_service import DiscoveryService, DiscoverySnapshot
from network.interface import get_network_status


class BasePage(Gtk.Box):
    def __init__(self, title: str, subtitle: str = "") -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self.set_margin_top(28); self.set_margin_bottom(28); self.set_margin_start(32); self.set_margin_end(32)
        heading = Gtk.Label(label=title, xalign=0); heading.add_css_class("title-1"); self.append(heading)
        if subtitle:
            label = Gtk.Label(label=subtitle, xalign=0, wrap=True); label.add_css_class("dim-label"); self.append(label)


def _section(title: str, child: Gtk.Widget) -> Gtk.Box:
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    heading = Gtk.Label(label=title, xalign=0); heading.add_css_class("heading"); box.append(heading); box.append(child)
    return box


class DashboardPage(BasePage):
    def __init__(self, config: Config, database: Database, state: ApplicationState) -> None:
        super().__init__("Dashboard", "NetFather Linux network management")
        self.database = database; self.state = state
        self.status = Gtk.Label(xalign=0, wrap=True); self.status.add_css_class("card"); self.append(self.status)
        self.refresh()
        button = Gtk.Button(label="Refresh"); button.set_halign(Gtk.Align.START); button.connect("clicked", lambda _b: self.refresh()); self.append(button)

    def refresh(self) -> None:
        network = get_network_status()
        with self.database.session() as session:
            count = session.scalar(select(func.count(Device.id))) or 0
            online = session.scalar(select(func.count(Device.id)).where(Device.online.is_(True))) or 0
        self.state.network.interface = network.interface; self.state.network.local_ip = network.local_ip; self.state.network.gateway = network.gateway
        self.state.network.known_devices = count; self.state.network.online_devices = online
        self.status.set_text(f"Interface: {network.interface or 'Unknown'}\nLocal IP: {network.local_ip or 'Unknown'}\nGateway: {network.gateway or 'Unknown'}\nRegistered devices: {count}\nOnline devices: {online}")


class DiscoveryPage(BasePage):
    def __init__(self, config: Config, database: Database, state: ApplicationState, tasks: BackgroundTaskRunner) -> None:
        super().__init__("Network Discovery", "Layered local-network discovery: Linux neighbor state, Scapy ARP and optional Nmap deep inventory.")
        self.config=config; self.database=database; self.state=state; self.tasks=tasks
        self.service=DiscoveryService(device_manager=DeviceManager(database)); self._pulse_source=None
        self._unsubscribe=state.subscribe(self._on_state_changed)
        self.summary=Gtk.Label(xalign=0,wrap=True); self.summary.add_css_class("dim-label"); self.append(self.summary)
        options=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12); options.add_css_class("card")
        row=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=12); label=Gtk.Label(label="Scan mode",xalign=0); label.set_hexpand(True); row.append(label)
        self.mode=Gtk.ComboBoxText()
        for value,title in (("passive","Passive"),("active","Active ARP"),("hybrid","Hybrid"),("deep","Deep inventory")):
            self.mode.append(value,title)
        self.mode.set_active_id(config.discovery.mode); row.append(self.mode); options.append(row)
        row=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=12); label=Gtk.Label(label="Subnet",xalign=0); label.set_hexpand(True); row.append(label)
        self.subnet=Gtk.Entry(); self.subnet.set_placeholder_text("Auto-detect local subnet"); self.subnet.set_text(config.discovery.subnet); self.subnet.set_width_chars(20); row.append(self.subnet); options.append(row)
        row=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=12); label=Gtk.Label(label="Discovery timeout (seconds)",xalign=0); label.set_hexpand(True); row.append(label)
        self.timeout=Gtk.SpinButton.new_with_range(1,60,1); self.timeout.set_value(config.network.scan_timeout_seconds); row.append(self.timeout); options.append(row)
        self.hostname=Gtk.CheckButton(label="Resolve hostnames"); self.hostname.set_active(config.discovery.hostname_resolution); options.append(self.hostname)
        self.vendor=Gtk.CheckButton(label="Detect hardware vendor"); self.vendor.set_active(config.discovery.vendor_detection); options.append(self.vendor)
        self.os_hint=Gtk.CheckButton(label="Estimate operating system"); self.os_hint.set_active(config.discovery.os_detection); options.append(self.os_hint)
        self.deep_box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8); self.deep_box.add_css_class("card")
        deep_title=Gtk.Label(label="Deep inventory",xalign=0); deep_title.add_css_class("heading"); self.deep_box.append(deep_title)
        deep_info=Gtk.Label(label="Uses Nmap when installed. Root/raw-packet privileges unlock SYN, UDP and OS fingerprinting; without them NetFather safely falls back to unprivileged TCP connect scanning.",xalign=0,wrap=True); deep_info.add_css_class("dim-label"); self.deep_box.append(deep_info)
        self.deep_udp=Gtk.CheckButton(label="Scan common UDP ports"); self.deep_udp.set_active(True); self.deep_box.append(self.deep_udp)
        self.deep_versions=Gtk.CheckButton(label="Identify services and versions"); self.deep_versions.set_active(True); self.deep_box.append(self.deep_versions)
        self.deep_os=Gtk.CheckButton(label="Fingerprint operating systems"); self.deep_os.set_active(True); self.deep_box.append(self.deep_os)
        row=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=12); label=Gtk.Label(label="Top TCP/UDP ports",xalign=0); label.set_hexpand(True); row.append(label)
        self.deep_ports=Gtk.SpinButton.new_with_range(10,1000,10); self.deep_ports.set_value(100); row.append(self.deep_ports); self.deep_box.append(row)
        options.append(self.deep_box)
        self.mode.connect("changed", lambda _c:self._update_deep_visibility())
        expander=Gtk.Expander(label="Scan options"); expander.set_child(options); expander.set_expanded(True); self.append(expander); self._update_deep_visibility()
        controls=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=10); self.scan_button=Gtk.Button(label="Start scan"); self.scan_button.add_css_class("suggested-action"); self.scan_button.connect("clicked",self._start_scan); controls.append(self.scan_button)
        self.last_scan=Gtk.Label(label="No scan run yet",xalign=0); self.last_scan.add_css_class("dim-label"); controls.append(self.last_scan); self.append(controls)
        self.progress=Gtk.ProgressBar(); self.progress.set_show_text(True); self.progress.set_text("Ready"); self.append(self.progress)
        self.status=Gtk.Label(label="Ready",xalign=0,wrap=True); self.status.add_css_class("card"); self.append(self.status)
        self.device_list=Gtk.ListBox(); self.device_list.set_selection_mode(Gtk.SelectionMode.NONE); self.device_list.set_vexpand(True); self.device_list.add_css_class("boxed-list"); self.append(_section("Discovered devices",self.device_list))
        self._render_devices(state.discovery.identities); self._on_state_changed()

    def _update_deep_visibility(self)->None:
        self.deep_box.set_visible((self.mode.get_active_id() or "hybrid") == "deep")

    def _start_scan(self,_button:Gtk.Button)->None:
        if self.state.discovery.running:return
        mode=self.mode.get_active_id() or "hybrid"; subnet=self.subnet.get_text().strip(); timeout=int(self.timeout.get_value())
        self.state.discovery.running=True; self.state.discovery.mode=mode; self.state.discovery.subnet=subnet; self.state.discovery.hostname_resolution=self.hostname.get_active(); self.state.discovery.vendor_detection=self.vendor.get_active(); self.state.discovery.os_detection=self.os_hint.get_active(); self.state.discovery.timeout_seconds=timeout; self.state.discovery.error=None; self.state.discovery.status_message=("Running deep local inventory..." if mode=="deep" else "Scanning local network..."); self.state.notify_changed(); self._start_pulse()
        self.tasks.submit(lambda:self.service.scan(timeout_seconds=timeout,active_timeout_seconds=self.config.discovery.active_timeout_seconds,mode=mode,subnet=subnet or None,hostname_resolution=self.hostname.get_active(),vendor_detection=self.vendor.get_active(),os_detection=self.os_hint.get_active(),deep_udp=self.deep_udp.get_active(),deep_versions=self.deep_versions.get_active(),deep_os=self.deep_os.get_active(),deep_top_ports=int(self.deep_ports.get_value())),self._scan_finished,self._scan_failed)

    def _scan_finished(self,snapshot:DiscoverySnapshot)->None:
        self.state.discovery.running=False; self.state.discovery.scanned=snapshot.scanned; self.state.discovery.identities=snapshot.identities; self.state.discovery.error=snapshot.error
        deep_hosts=len(snapshot.deep_hosts); service_count=sum(len(h.services) for h in snapshot.deep_hosts); port_count=sum(len(h.open_tcp_ports)+len(h.open_udp_ports) for h in snapshot.deep_hosts)
        detail=f"Deep inventory: {deep_hosts} host(s), {port_count} open port(s), {service_count} service fingerprint(s)." if deep_hosts else ""
        self.state.discovery.status_message=(f"Scan completed: {snapshot.scanned} host(s) observed. New {snapshot.new_devices}, updated {snapshot.updated_devices}, offline {snapshot.offline_devices}. {detail}" if snapshot.error is None else snapshot.error)
        self.state.notify_changed(); self._stop_pulse(); self.last_scan.set_text(f"Completed at {snapshot.completed_at.astimezone().strftime('%H:%M:%S')}")

    def _scan_failed(self,error:BaseException)->None:
        self.state.discovery.running=False; self.state.discovery.error=str(error); self.state.discovery.status_message=str(error); self.state.notify_changed(); self._stop_pulse()

    def _on_state_changed(self)->None:
        d=self.state.discovery; self.scan_button.set_sensitive(not d.running); self.progress.set_text("Scanning..." if d.running else ("Error" if d.error else "Ready")); self.status.set_text(d.status_message)
        online=sum(1 for i in d.identities if i.online); self.summary.set_text(f"Observed: {d.scanned}   |   Known identities: {len(d.identities)}   |   Online: {online}"); self._render_devices(d.identities)

    def _render_devices(self,identities)->None:
        while (child:=self.device_list.get_first_child()) is not None:self.device_list.remove(child)
        if not identities:
            empty=Gtk.Label(label="No devices discovered yet.",xalign=0); empty.add_css_class("dim-label"); self.device_list.append(empty); return
        for identity in sorted(identities,key=lambda i:(not i.online,i.current_ip or i.mac)):
            row=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=3); row.set_margin_top(10); row.set_margin_bottom(10); row.set_margin_start(12); row.set_margin_end(12)
            title=Gtk.Label(label=f"{'Online' if identity.online else 'Offline'}  {identity.current_ip or 'No IP'}",xalign=0); title.add_css_class("heading"); row.append(title)
            details=[identity.mac]; details += [sorted(identity.hostnames)[0]] if identity.hostnames else []; details += [sorted(identity.vendors)[0]] if identity.vendors else []; details += [sorted(identity.os_hints)[0]] if identity.os_hints else []; details.append(f"Confidence {identity.confidence:.0%}")
            info=Gtk.Label(label="  |  ".join(details),xalign=0,wrap=True); info.add_css_class("dim-label"); row.append(info); self.device_list.append(row)
        deep=self.service.snapshot.deep_hosts if self.service.snapshot else ()
        if deep:
            heading=Gtk.Label(label="Deep scan findings",xalign=0); heading.add_css_class("heading"); self.device_list.append(heading)
            for host in sorted(deep,key=lambda h:h.ip):
                ports=", ".join(str(p) for p in (*host.open_tcp_ports,*host.open_udp_ports)) or "none"
                services="; ".join(host.services) or "No service fingerprint"
                text=f"{host.ip}  |  TCP/UDP open: {ports}\n{services}"
                row=Gtk.Label(label=text,xalign=0,wrap=True); row.set_margin_top(8); row.set_margin_bottom(8); row.set_margin_start(12); row.set_margin_end(12); self.device_list.append(row)

    def _start_pulse(self):
        if self._pulse_source is None:self._pulse_source=GLib.timeout_add(120,self._pulse_progress)
    def _pulse_progress(self)->bool:
        if not self.state.discovery.running:self._pulse_source=None; return GLib.SOURCE_REMOVE
        self.progress.pulse(); return GLib.SOURCE_CONTINUE
    def _stop_pulse(self):
        if self._pulse_source is not None:GLib.source_remove(self._pulse_source); self._pulse_source=None
        self.progress.set_fraction(1.0 if not self.state.discovery.error else 0.0)


class DevicesPage(BasePage):
    """Registered device management workspace."""
    def __init__(self,database:Database,state:ApplicationState,tasks:BackgroundTaskRunner)->None:
        super().__init__("Devices","Manage registered devices and inspect their current network identity.")
        self.state=state; self.tasks=tasks; self.service=DeviceService(database); self.selected_name=None; self._busy=False; self._confirm_delete=False
        self._unsubscribe=state.subscribe(self._on_state_changed)
        toolbar=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=10); self.refresh_button=Gtk.Button(label="Refresh"); self.refresh_button.connect("clicked",lambda _b:self.refresh()); toolbar.append(self.refresh_button); self.count_label=Gtk.Label(xalign=0); self.count_label.add_css_class("dim-label"); toolbar.append(self.count_label); self.append(toolbar)
        content=Gtk.Paned.new(Gtk.Orientation.HORIZONTAL); content.set_wide_handle(True); content.set_vexpand(True); self.append(content)
        self.list_box=Gtk.ListBox(); self.list_box.set_selection_mode(Gtk.SelectionMode.SINGLE); self.list_box.add_css_class("boxed-list"); self.list_box.set_vexpand(True); self.list_box.connect("row-selected",self._on_row_selected); content.set_start_child(self.list_box)
        detail=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12); detail.set_margin_start(24); detail.set_margin_end(8); detail.set_vexpand(True); content.set_end_child(detail)
        self.detail_title=Gtk.Label(label="Select a device",xalign=0); self.detail_title.add_css_class("title-2"); detail.append(self.detail_title); self.detail_status=Gtk.Label(xalign=0,wrap=True); self.detail_status.add_css_class("dim-label"); detail.append(self.detail_status)
        self.name_entry=Gtk.Entry(); self.ip_entry=Gtk.Entry(); self.vendor_entry=Gtk.Entry(); self.type_entry=Gtk.Entry()
        self.name_entry.set_placeholder_text("Device name"); self.ip_entry.set_placeholder_text("Current IP"); self.vendor_entry.set_placeholder_text("Vendor"); self.type_entry.set_placeholder_text("unknown")
        for label,entry in (("Name",self.name_entry),("IP address",self.ip_entry),("Vendor",self.vendor_entry),("Device type",self.type_entry)):detail.append(self._field(label,entry))
        self.save_button=Gtk.Button(label="Save changes"); self.save_button.add_css_class("suggested-action"); self.save_button.connect("clicked",self._save); detail.append(self.save_button)
        self.delete_button=Gtk.Button(label="Delete device"); self.delete_button.add_css_class("destructive-action"); self.delete_button.connect("clicked",self._delete); detail.append(self.delete_button)
        self.message=Gtk.Label(xalign=0,wrap=True); detail.append(self.message); self._set_detail(None); self.refresh()

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
            row=Gtk.ListBoxRow(); row.set_name(device.name); box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=3); box.set_margin_top(10); box.set_margin_bottom(10); box.set_margin_start(12); box.set_margin_end(12)
            name=Gtk.Label(label=device.name,xalign=0); name.add_css_class("heading"); box.append(name); meta=Gtk.Label(label=f"{'Online' if device.online else 'Offline'}  |  {device.ip or 'No IP'}  |  {device.mac}",xalign=0); meta.add_css_class("dim-label"); box.append(meta); row.set_child(box); self.list_box.append(row)
    def _on_row_selected(self,_list,row)->None:
        self._confirm_delete=False; self.selected_name=row.get_name() if row else None; self._set_detail(next((d for d in self.service.snapshot.devices if d.name==self.selected_name),None))
    def _set_detail(self,device:Device|None)->None:
        enabled=device is not None and not self._busy
        for entry in (self.name_entry,self.ip_entry,self.vendor_entry,self.type_entry):entry.set_sensitive(enabled)
        self.save_button.set_sensitive(enabled); self.delete_button.set_sensitive(enabled); self.message.set_text("") if device is None else None
        if device is None:
            self.detail_title.set_text("Select a device"); self.detail_status.set_text("Choose a device from the list to inspect and edit it."); [e.set_text("") for e in (self.name_entry,self.ip_entry,self.vendor_entry,self.type_entry)]; return
        self.detail_title.set_text(device.name); last=self._format_time(device.last_seen); self.detail_status.set_text(f"MAC: {device.mac}\nHostname: {device.hostname or 'Unknown'}\nOS hint: {device.os_hint or 'Unknown'}\nStatus: {'Online' if device.online else 'Offline'}\nLast seen: {last}\nRegistration: {'Automatic discovery' if device.auto_registered else 'Manual'}")
        self.name_entry.set_text(device.name); self.ip_entry.set_text(device.ip or ""); self.vendor_entry.set_text(device.vendor or ""); self.type_entry.set_text(device.device_type or "unknown")
    @staticmethod
    def _format_time(value:datetime|None)->str:return "Never" if value is None else value.astimezone().strftime("%Y-%m-%d %H:%M:%S")
    def _save(self,_button)->None:
        if not self.selected_name or self._busy:return
        current=self.selected_name; new_name=self.name_entry.get_text().strip(); ip=self.ip_entry.get_text().strip() or None; vendor=self.vendor_entry.get_text().strip() or None; dtype=self.type_entry.get_text().strip() or "unknown"
        if not new_name:self.message.set_text("Device name cannot be empty."); return
        self._busy=True; self._set_detail(next((d for d in self.service.snapshot.devices if d.name==current),None)); self.tasks.submit(lambda:self.service.update(current,new_name=new_name,ip=ip,vendor=vendor,device_type=dtype),self._save_finished,self._operation_failed)
    def _save_finished(self,snapshot:DeviceSnapshot)->None:
        self.selected_name=snapshot.selected_name; self._refresh_finished(snapshot); self.message.set_text("Device changes saved.")
    def _delete(self,_button)->None:
        if not self.selected_name or self._busy:return
        if not self._confirm_delete:self._confirm_delete=True; self.message.set_text("Click Delete device again to permanently remove this device."); return
        name=self.selected_name; self._busy=True; self._set_detail(next((d for d in self.service.snapshot.devices if d.name==name),None)); self.tasks.submit(lambda:self.service.delete(name),self._delete_finished,self._operation_failed)
    def _delete_finished(self,snapshot:DeviceSnapshot)->None:
        self._busy=False; self._confirm_delete=False; self.selected_name=None; self._refresh_finished(snapshot); self.message.set_text("Device deleted.")
    def _operation_failed(self,error:BaseException)->None:
        self._busy=False; self.refresh_button.set_sensitive(True); self._set_detail(next((d for d in self.service.snapshot.devices if d.name==self.selected_name),None)); self.message.set_text(str(error)); self.message.add_css_class("error")
    def _on_state_changed(self)->None:
        if not self.state.discovery.running:self.refresh()


class PlaceholderPage(BasePage):
    def __init__(self,title:str,message:str)->None:super().__init__(title,message)
