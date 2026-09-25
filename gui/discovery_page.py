"""Network discovery GTK page."""
from __future__ import annotations

from gi.repository import GLib, Gtk
from core.config import Config
from core.database import Database
from gui.base_page import BasePage, section
from gui.state import ApplicationState
from gui.tasks import BackgroundTaskRunner
from manager.device_manager import DeviceManager
from network.discovery_service import DiscoveryService, DiscoverySnapshot

class DiscoveryPage(BasePage):
    def __init__(self,config:Config,database:Database,state:ApplicationState,tasks:BackgroundTaskRunner)->None:
        super().__init__("Network Discovery","Layered local-network discovery: Linux neighbor state, Scapy ARP and optional Nmap deep inventory."); self.config=config; self.database=database; self.state=state; self.tasks=tasks; self.service=DiscoveryService(device_manager=DeviceManager(database)); self._pulse_source=None; self._unsubscribe=state.subscribe(self._on_state_changed)
        self.summary=Gtk.Label(xalign=0,wrap=True); self.summary.add_css_class("dim-label"); self.append(self.summary)
        options=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12); options.add_css_class("card")
        row=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=12); label=Gtk.Label(label="Scan mode",xalign=0); label.set_hexpand(True); row.append(label); self.mode=Gtk.ComboBoxText()
        for value,title in (("passive","Passive"),("active","Active ARP"),("hybrid","Hybrid"),("deep","Deep inventory")): self.mode.append(value,title)
        self.mode.set_active_id(config.discovery.mode); row.append(self.mode); options.append(row)
        row=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=12); label=Gtk.Label(label="Subnet",xalign=0); label.set_hexpand(True); row.append(label); self.subnet=Gtk.Entry(); self.subnet.set_placeholder_text("Auto-detect local subnet"); self.subnet.set_text(config.discovery.subnet); self.subnet.set_width_chars(20); row.append(self.subnet); options.append(row)
        row=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=12); label=Gtk.Label(label="Discovery timeout (seconds)",xalign=0); label.set_hexpand(True); row.append(label); self.timeout=Gtk.SpinButton.new_with_range(1,60,1); self.timeout.set_value(config.network.scan_timeout_seconds); row.append(self.timeout); options.append(row)
        self.hostname=Gtk.CheckButton(label="Resolve hostnames"); self.hostname.set_active(config.discovery.hostname_resolution); options.append(self.hostname); self.vendor=Gtk.CheckButton(label="Detect hardware vendor"); self.vendor.set_active(config.discovery.vendor_detection); options.append(self.vendor); self.os_hint=Gtk.CheckButton(label="Estimate operating system"); self.os_hint.set_active(config.discovery.os_detection); options.append(self.os_hint)
        self.deep_box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8); self.deep_box.add_css_class("card"); deep_title=Gtk.Label(label="Deep inventory",xalign=0); deep_title.add_css_class("heading"); self.deep_box.append(deep_title)
        deep_info=Gtk.Label(label="Nmap service/version discovery, TCP/UDP coverage and OS fingerprinting. Elevated mode asks for authorization only for the Nmap process; the GTK application remains unprivileged.",xalign=0,wrap=True); deep_info.add_css_class("dim-label"); self.deep_box.append(deep_info)
        self.deep_udp=Gtk.CheckButton(label="Scan common UDP ports"); self.deep_udp.set_active(True); self.deep_box.append(self.deep_udp); self.deep_versions=Gtk.CheckButton(label="Identify services and versions"); self.deep_versions.set_active(True); self.deep_box.append(self.deep_versions); self.deep_os=Gtk.CheckButton(label="Fingerprint operating systems"); self.deep_os.set_active(True); self.deep_box.append(self.deep_os); self.deep_elevate=Gtk.CheckButton(label="Use elevated scan via system authorization"); self.deep_elevate.set_active(False); self.deep_box.append(self.deep_elevate)
        row=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=12); label=Gtk.Label(label="Top TCP/UDP ports",xalign=0); label.set_hexpand(True); row.append(label); self.deep_ports=Gtk.SpinButton.new_with_range(10,1000,10); self.deep_ports.set_value(100); row.append(self.deep_ports); self.deep_box.append(row); options.append(self.deep_box)
        self.mode.connect("changed",lambda _c:self._update_deep_visibility()); expander=Gtk.Expander(label="Scan options"); expander.set_child(options); expander.set_expanded(True); self.append(expander); self._update_deep_visibility()
        controls=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=10); self.scan_button=Gtk.Button(label="Start scan"); self.scan_button.add_css_class("suggested-action"); self.scan_button.connect("clicked",self._start_scan); controls.append(self.scan_button); self.last_scan=Gtk.Label(label="No scan run yet",xalign=0); self.last_scan.add_css_class("dim-label"); controls.append(self.last_scan); self.append(controls)
        self.progress=Gtk.ProgressBar(); self.progress.set_show_text(True); self.progress.set_text("Ready"); self.append(self.progress); self.status=Gtk.Label(label="Ready",xalign=0,wrap=True); self.status.add_css_class("card"); self.append(self.status); self.device_list=Gtk.ListBox(); self.device_list.set_selection_mode(Gtk.SelectionMode.NONE); self.device_list.set_vexpand(True); self.device_list.add_css_class("boxed-list"); self.append(section("Discovered devices",self.device_list)); self._render_devices(state.discovery.identities); self._on_state_changed()
    def _update_deep_visibility(self)->None:self.deep_box.set_visible((self.mode.get_active_id() or "hybrid")=="deep")
    def _start_scan(self,_button:Gtk.Button)->None:
        if self.state.discovery.running:return
        mode=self.mode.get_active_id() or "hybrid"; subnet=self.subnet.get_text().strip(); timeout=int(self.timeout.get_value()); self.state.discovery.running=True; self.state.discovery.mode=mode; self.state.discovery.subnet=subnet; self.state.discovery.hostname_resolution=self.hostname.get_active(); self.state.discovery.vendor_detection=self.vendor.get_active(); self.state.discovery.os_detection=self.os_hint.get_active(); self.state.discovery.timeout_seconds=timeout; self.state.discovery.error=None; self.state.discovery.status_message=("Running deep local inventory..." if mode=="deep" else "Scanning local network..."); self.state.notify_changed(); self._start_pulse()
        self.tasks.submit(lambda:self.service.scan(timeout_seconds=timeout,active_timeout_seconds=self.config.discovery.active_timeout_seconds,mode=mode,subnet=subnet or None,hostname_resolution=self.hostname.get_active(),vendor_detection=self.vendor.get_active(),os_detection=self.os_hint.get_active(),deep_udp=self.deep_udp.get_active(),deep_versions=self.deep_versions.get_active(),deep_os=self.deep_os.get_active(),deep_top_ports=int(self.deep_ports.get_value()),deep_elevate=self.deep_elevate.get_active()),self._scan_finished,self._scan_failed)
    def _scan_finished(self,snapshot:DiscoverySnapshot)->None:
        self.state.discovery.running=False; self.state.discovery.scanned=snapshot.scanned; self.state.discovery.identities=snapshot.identities; self.state.discovery.error=snapshot.error; deep_hosts=len(snapshot.deep_hosts); service_count=sum(len(h.services) for h in snapshot.deep_hosts); port_count=sum(len(h.open_tcp_ports)+len(h.open_udp_ports) for h in snapshot.deep_hosts); detail=f"Deep inventory: {deep_hosts} host(s), {port_count} open port(s), {service_count} service fingerprint(s)." if deep_hosts else ""; self.state.discovery.status_message=(f"Scan completed: {snapshot.scanned} host(s) observed. New {snapshot.new_devices}, updated {snapshot.updated_devices}, offline {snapshot.offline_devices}. {detail}" if snapshot.error is None else snapshot.error); self.state.notify_changed(); self._stop_pulse(); self.last_scan.set_text(f"Completed at {snapshot.completed_at.astimezone().strftime('%H:%M:%S')}")
    def _scan_failed(self,error:BaseException)->None:self.state.discovery.running=False; self.state.discovery.error=str(error); self.state.discovery.status_message=str(error); self.state.notify_changed(); self._stop_pulse()
    def _on_state_changed(self)->None:
        d=self.state.discovery; self.scan_button.set_sensitive(not d.running); self.progress.set_text("Scanning..." if d.running else ("Error" if d.error else "Ready")); self.status.set_text(d.status_message); online=sum(1 for i in d.identities if i.online); self.summary.set_text(f"Observed: {d.scanned}   |   Known identities: {len(d.identities)}   |   Online: {online}"); self._render_devices(d.identities)
    def _render_devices(self,identities)->None:
        while (child:=self.device_list.get_first_child()) is not None:self.device_list.remove(child)
        if not identities: empty=Gtk.Label(label="No devices discovered yet.",xalign=0); empty.add_css_class("dim-label"); self.device_list.append(empty); return
        for identity in sorted(identities,key=lambda i:(not i.online,i.current_ip or i.mac)):
            row=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=3); row.set_margin_top(10); row.set_margin_bottom(10); row.set_margin_start(12); row.set_margin_end(12); title=Gtk.Label(label=f"{'Online' if identity.online else 'Offline'}  {identity.current_ip or 'No IP'}",xalign=0); title.add_css_class("heading"); row.append(title); details=[identity.mac]; details += [sorted(identity.hostnames)[0]] if identity.hostnames else []; details += [sorted(identity.vendors)[0]] if identity.vendors else []; details += [sorted(identity.os_hints)[0]] if identity.os_hints else []; details.append(f"Confidence {identity.confidence:.0%}"); info=Gtk.Label(label="  |  ".join(details),xalign=0,wrap=True); info.add_css_class("dim-label"); row.append(info); self.device_list.append(row)
        deep=self.service.snapshot.deep_hosts if self.service.snapshot else ()
        if deep:
            heading=Gtk.Label(label="Deep scan findings",xalign=0); heading.add_css_class("heading"); self.device_list.append(heading)
            for host in sorted(deep,key=lambda h:h.ip):
                ports=", ".join(str(p) for p in (*host.open_tcp_ports,*host.open_udp_ports)) or "none"; services="; ".join(host.services) or "No service fingerprint"; text=f"{host.ip}  |  TCP/UDP open: {ports}\n{services}"; row=Gtk.Label(label=text,xalign=0,wrap=True); row.set_margin_top(8); row.set_margin_bottom(8); row.set_margin_start(12); row.set_margin_end(12); self.device_list.append(row)
    def _start_pulse(self):
        if self._pulse_source is None:self._pulse_source=GLib.timeout_add(120,self._pulse_progress)
    def _pulse_progress(self)->bool:
        if not self.state.discovery.running:self._pulse_source=None; return GLib.SOURCE_REMOVE
        self.progress.pulse(); return GLib.SOURCE_CONTINUE
    def _stop_pulse(self):
        if self._pulse_source is not None:GLib.source_remove(self._pulse_source); self._pulse_source=None
        self.progress.set_fraction(1.0 if not self.state.discovery.error else 0.0)

