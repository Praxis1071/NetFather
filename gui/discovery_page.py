"""Network discovery GTK page."""
from __future__ import annotations

from core.i18n import tr

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
        super().__init__(tr('Network Discovery'),tr('Layered local-network discovery: Linux neighbor state, Scapy ARP and optional Nmap deep inventory.')); self.config=config; self.database=database; self.state=state; self.tasks=tasks; self.service=DiscoveryService(device_manager=DeviceManager(database)); self._pulse_source=None; self._unsubscribe=state.subscribe(self._on_state_changed)
        self.summary=Gtk.Label(xalign=0,wrap=True); self.summary.add_css_class("dim-label"); self.append(self.summary)
        options=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12); options.add_css_class("card")
        row=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=12); label=Gtk.Label(label=tr('Scan mode'),xalign=0); label.set_hexpand(True); row.append(label); self.mode=Gtk.ComboBoxText()
        for value,title in (("passive",tr('Passive')),("active",tr('Active ARP')),("hybrid",tr('Hybrid')),("deep",tr('Deep inventory'))): self.mode.append(value,title)
        self.mode.set_active_id(config.discovery.mode); row.append(self.mode); options.append(row)
        row=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=12); label=Gtk.Label(label=tr('Subnet'),xalign=0); label.set_hexpand(True); row.append(label); self.subnet=Gtk.Entry(); self.subnet.set_placeholder_text(tr('Auto-detect local subnet')); self.subnet.set_text(config.discovery.subnet); self.subnet.set_width_chars(20); row.append(self.subnet); options.append(row)
        row=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=12); label=Gtk.Label(label=tr('Discovery timeout (seconds)'),xalign=0); label.set_hexpand(True); row.append(label); self.timeout=Gtk.SpinButton.new_with_range(1,60,1); self.timeout.set_value(config.network.scan_timeout_seconds); row.append(self.timeout); options.append(row)
        self.hostname=Gtk.CheckButton(label=tr('Resolve hostnames')); self.hostname.set_active(config.discovery.hostname_resolution); options.append(self.hostname); self.vendor=Gtk.CheckButton(label=tr('Detect hardware vendor')); self.vendor.set_active(config.discovery.vendor_detection); options.append(self.vendor); self.os_hint=Gtk.CheckButton(label=tr('Estimate operating system')); self.os_hint.set_active(config.discovery.os_detection); options.append(self.os_hint)
        self.deep_box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8); self.deep_box.add_css_class("card"); deep_title=Gtk.Label(label=tr('Deep inventory'),xalign=0); deep_title.add_css_class("heading"); self.deep_box.append(deep_title)
        deep_info=Gtk.Label(label=tr('Nmap service/version discovery, TCP/UDP coverage and OS fingerprinting. Elevated mode asks for authorization only for the Nmap process; the GTK application remains unprivileged.'),xalign=0,wrap=True); deep_info.add_css_class("dim-label"); self.deep_box.append(deep_info)
        self.deep_udp=Gtk.CheckButton(label=tr('Scan common UDP ports')); self.deep_udp.set_active(True); self.deep_box.append(self.deep_udp); self.deep_versions=Gtk.CheckButton(label=tr('Identify services and versions')); self.deep_versions.set_active(True); self.deep_box.append(self.deep_versions); self.deep_os=Gtk.CheckButton(label=tr('Fingerprint operating systems')); self.deep_os.set_active(True); self.deep_box.append(self.deep_os); self.deep_elevate=Gtk.CheckButton(label=tr('Use elevated scan via system authorization')); self.deep_elevate.set_active(False); self.deep_box.append(self.deep_elevate)
        row=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=12); label=Gtk.Label(label=tr('Top TCP/UDP ports'),xalign=0); label.set_hexpand(True); row.append(label); self.deep_ports=Gtk.SpinButton.new_with_range(10,1000,10); self.deep_ports.set_value(100); row.append(self.deep_ports); self.deep_box.append(row); options.append(self.deep_box)
        self.mode.connect("changed",lambda _c:self._update_deep_visibility()); expander=Gtk.Expander(label=tr('Scan options')); expander.set_child(options); expander.set_expanded(True); self.append(expander); self._update_deep_visibility()
        controls=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=10); self.scan_button=Gtk.Button(label=tr('Start scan')); self.scan_button.add_css_class("suggested-action"); self.scan_button.connect("clicked",self._start_scan); controls.append(self.scan_button); self.last_scan=Gtk.Label(label=tr('No scan run yet'),xalign=0); self.last_scan.add_css_class("dim-label"); controls.append(self.last_scan); self.append(controls)
        self.progress=Gtk.ProgressBar(); self.progress.set_show_text(True); self.progress.set_text(tr('Ready')); self.append(self.progress); self.status=Gtk.Label(label=tr('Ready'),xalign=0,wrap=True); self.status.add_css_class("card"); self.append(self.status); self.device_list=Gtk.ListBox(); self.device_list.set_selection_mode(Gtk.SelectionMode.NONE); self.device_list.set_vexpand(True); self.device_list.add_css_class("boxed-list"); self.append(section(tr('Discovered devices'),self.device_list)); self._render_devices(state.discovery.identities); self._on_state_changed()
    def cleanup(self)->None:
        if self._pulse_source is not None:
            GLib.source_remove(self._pulse_source)
            self._pulse_source = None
        self._unsubscribe()

    def _update_deep_visibility(self)->None:self.deep_box.set_visible((self.mode.get_active_id() or "hybrid")=="deep")
    def _start_scan(self,_button:Gtk.Button)->None:
        if self.state.discovery.running:return
        # Read GTK controls on the main thread. Worker threads must only receive
        # immutable values, never query GTK widgets.
        mode=self.mode.get_active_id() or "hybrid"
        subnet=self.subnet.get_text().strip()
        timeout=int(self.timeout.get_value())
        hostname_resolution=self.hostname.get_active()
        vendor_detection=self.vendor.get_active()
        os_detection=self.os_hint.get_active()
        deep_udp=self.deep_udp.get_active()
        deep_versions=self.deep_versions.get_active()
        deep_os=self.deep_os.get_active()
        deep_top_ports=int(self.deep_ports.get_value())
        deep_elevate=self.deep_elevate.get_active()
        active_timeout_seconds=self.config.discovery.active_timeout_seconds
        auto_register=self.config.discovery.auto_register
        offline_after_seconds=self.config.discovery.offline_after_seconds
        self.state.discovery.running=True
        self.state.discovery.mode=mode
        self.state.discovery.subnet=subnet
        self.state.discovery.hostname_resolution=hostname_resolution
        self.state.discovery.vendor_detection=vendor_detection
        self.state.discovery.os_detection=os_detection
        self.state.discovery.timeout_seconds=timeout
        self.state.discovery.error=None
        self.state.discovery.status_message=(tr('Running deep local inventory...') if mode=="deep" else tr('Scanning local network...'))
        self.state.notify_changed()
        self._start_pulse()
        self.tasks.submit(
            lambda:self.service.scan(
                timeout_seconds=timeout,
                active_timeout_seconds=active_timeout_seconds,
                mode=mode,
                subnet=subnet or None,
                hostname_resolution=hostname_resolution,
                vendor_detection=vendor_detection,
                os_detection=os_detection,
                deep_udp=deep_udp,
                deep_versions=deep_versions,
                deep_os=deep_os,
                deep_top_ports=deep_top_ports,
                deep_elevate=deep_elevate,
                auto_register=auto_register,
                offline_after_seconds=offline_after_seconds,
            ),
            self._scan_finished,
            self._scan_failed,
        )
    def _scan_finished(self,snapshot:DiscoverySnapshot)->None:
        discovery = self.state.discovery
        discovery.running = False
        discovery.scanned = snapshot.scanned
        discovery.identities = snapshot.identities
        discovery.error = snapshot.error
        deep_hosts = len(snapshot.deep_hosts)
        service_count = sum(len(h.services) for h in snapshot.deep_hosts)
        port_count = sum(len(h.open_tcp_ports) + len(h.open_udp_ports) for h in snapshot.deep_hosts)
        detail = tr('Deep inventory: {v0} host(s), {v1} open port(s), {v2} service fingerprint(s).', v0=deep_hosts, v1=port_count, v2=service_count) if deep_hosts else ""
        if snapshot.error:
            message = snapshot.error
        else:
            status = tr('Scan completed') if snapshot.complete else tr('Partial scan')
            message = tr('{v0}: {v1} host(s) observed. New {v2}, updated {v3}, offline {v4}. {v5}', v0=status, v1=snapshot.scanned, v2=snapshot.new_devices, v3=snapshot.updated_devices, v4=snapshot.offline_devices, v5=detail)
            if not snapshot.complete:
                message += tr(' Missing devices kept in their previous state.')
        if snapshot.warnings:
            message += "\n" + "\n".join(snapshot.warnings)
        discovery.status_message = message
        self.state.notify_changed()
        self._stop_pulse()
        self.last_scan.set_text(tr('Completed at {v0}', v0=snapshot.completed_at.astimezone().strftime('%H:%M:%S')))
    def _scan_failed(self,error:BaseException)->None:self.state.discovery.running=False; self.state.discovery.error=str(error); self.state.discovery.status_message=tr("Operation failed: {error}", error=error); self.state.notify_changed(); self._stop_pulse()
    def _on_state_changed(self)->None:
        d=self.state.discovery; self.scan_button.set_sensitive(not d.running); self.progress.set_text(tr('Scanning...') if d.running else (tr('Error') if d.error else tr('Ready'))); self.status.set_text(d.status_message); online=sum(1 for i in d.identities if i.online); self.summary.set_text(tr('Observed: {v0}   |   Known identities: {v1}   |   Online: {v2}', v0=d.scanned, v1=len(d.identities), v2=online)); self._render_devices(d.identities)
    def _render_devices(self,identities)->None:
        while (child:=self.device_list.get_first_child()) is not None:self.device_list.remove(child)
        if not identities: empty=Gtk.Label(label=tr('No devices discovered yet.'),xalign=0); empty.add_css_class("dim-label"); self.device_list.append(empty); return
        for identity in sorted(identities,key=lambda i:(not i.online,i.current_ip or i.mac)):
            row=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=3); row.set_margin_top(10); row.set_margin_bottom(10); row.set_margin_start(12); row.set_margin_end(12); title=Gtk.Label(label=f"{tr('Online') if identity.online else tr('Offline')}  {identity.current_ip or tr('No IP')}",xalign=0); title.add_css_class("heading"); row.append(title); details=[identity.mac]; details += [sorted(identity.hostnames)[0]] if identity.hostnames else []; details += [sorted(identity.vendors)[0]] if identity.vendors else []; details += [sorted(identity.os_hints)[0]] if identity.os_hints else []; details.append(tr('Confidence {v0:.0%}', v0=identity.confidence)); info=Gtk.Label(label="  |  ".join(details),xalign=0,wrap=True); info.add_css_class("dim-label"); row.append(info); self.device_list.append(row)
        deep=self.service.snapshot.deep_hosts if self.service.snapshot else ()
        if deep:
            heading=Gtk.Label(label=tr('Deep scan findings'),xalign=0); heading.add_css_class("heading"); self.device_list.append(heading)
            for host in sorted(deep,key=lambda h:h.ip):
                ports=", ".join(str(p) for p in (*host.open_tcp_ports,*host.open_udp_ports)) or tr("None"); services="; ".join(host.services) or tr('No service fingerprint'); text=tr('{v0}  |  TCP/UDP open: {v1}\n{v2}', v0=host.ip, v1=ports, v2=services); row=Gtk.Label(label=text,xalign=0,wrap=True); row.set_margin_top(8); row.set_margin_bottom(8); row.set_margin_start(12); row.set_margin_end(12); self.device_list.append(row)
    def _start_pulse(self):
        if self._pulse_source is None:self._pulse_source=GLib.timeout_add(120,self._pulse_progress)
    def _pulse_progress(self)->bool:
        if not self.state.discovery.running:self._pulse_source=None; return GLib.SOURCE_REMOVE
        self.progress.pulse(); return GLib.SOURCE_CONTINUE
    def _stop_pulse(self):
        if self._pulse_source is not None:GLib.source_remove(self._pulse_source); self._pulse_source=None
        self.progress.set_fraction(1.0 if not self.state.discovery.error else 0.0)
