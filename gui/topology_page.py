"""GTK4 network topology workspace."""
from __future__ import annotations

from gi.repository import GLib, Gtk

from core.database import Database
from gui.tasks import BackgroundTaskRunner
from network.topology import NetworkTopology, TopologyNode, build_topology


class TopologyPage(Gtk.Box):
    """Render a live logical topology without inventing physical links."""

    def __init__(self, database: Database, tasks: BackgroundTaskRunner) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self.set_margin_top(28)
        self.set_margin_bottom(28)
        self.set_margin_start(32)
        self.set_margin_end(32)
        self.database = database
        self.tasks = tasks
        self._busy = False
        self._refresh_source: int | None = None

        heading = Gtk.Label(label="Network Topology", xalign=0)
        heading.add_css_class("title-1")
        self.append(heading)
        subtitle = Gtk.Label(
            label="Live logical view of the local gateway and devices observed by NetFather.",
            xalign=0,
            wrap=True,
        )
        subtitle.add_css_class("dim-label")
        self.append(subtitle)

        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.refresh_button = Gtk.Button(label="Refresh topology")
        self.refresh_button.add_css_class("suggested-action")
        self.refresh_button.connect("clicked", lambda _button: self.refresh())
        toolbar.append(self.refresh_button)
        self.summary = Gtk.Label(xalign=0)
        self.summary.add_css_class("dim-label")
        toolbar.append(self.summary)
        self.append(toolbar)

        self.status = Gtk.Label(label="Ready", xalign=0, wrap=True)
        self.append(self.status)

        self.scroller = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
        self.scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.list_box = Gtk.ListBox()
        self.list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        self.list_box.set_vexpand(True)
        self.list_box.add_css_class("boxed-list")
        self.scroller.set_child(self.list_box)
        self.append(self.scroller)

        self.refresh()
        self._refresh_source = GLib.timeout_add_seconds(3, self._periodic_refresh)

    def _periodic_refresh(self) -> bool:
        if not self._busy:
            self.refresh()
        return GLib.SOURCE_CONTINUE

    def refresh(self) -> None:
        if self._busy:
            return
        self._busy = True
        self.refresh_button.set_sensitive(False)
        self.status.set_text("Refreshing network topology...")
        self.tasks.submit(
            lambda: build_topology(self.database),
            self._refresh_finished,
            self._refresh_failed,
        )

    def _refresh_finished(self, topology: NetworkTopology) -> None:
        self._busy = False
        self.refresh_button.set_sensitive(True)
        self._render(topology)
        devices = [node for node in topology.nodes if node.kind != "router"]
        online = sum(1 for node in devices if node.online)
        restricted = sum(1 for node in devices if not node.allowed)
        gateway = next((node for node in topology.nodes if node.kind == "router"), None)
        gateway_text = gateway.ip if gateway and gateway.ip else "Unknown"
        self.summary.set_text(
            f"Gateway {gateway_text}  |  {len(devices)} devices  |  {online} online  |  {restricted} restricted"
        )
        self.status.set_text("Live topology updated.")

    def _refresh_failed(self, error: BaseException) -> None:
        self._busy = False
        self.refresh_button.set_sensitive(True)
        self.status.set_text(f"Topology update failed: {error}")

    def _render(self, topology: NetworkTopology) -> None:
        while (child := self.list_box.get_first_child()) is not None:
            self.list_box.remove(child)

        router = next((node for node in topology.nodes if node.kind == "router"), None)
        if router is None:
            self.list_box.append(Gtk.Label(label="No gateway information available.", xalign=0))
            return

        self.list_box.append(self._node_row(router, is_router=True))
        devices = [node for node in topology.nodes if node.kind != "router"]
        if not devices:
            empty = Gtk.Label(label="No registered devices yet.", xalign=0.5)
            empty.set_margin_top(24)
            empty.add_css_class("dim-label")
            self.list_box.append(empty)
            return

        for node in devices:
            connector = Gtk.Label(label="│", xalign=0.5)
            connector.add_css_class("dim-label")
            self.list_box.append(connector)
            self.list_box.append(self._node_row(node))

    @staticmethod
    def _node_row(node: TopologyNode, *, is_router: bool = False) -> Gtk.Box:
        row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        row.set_margin_top(10)
        row.set_margin_bottom(10)
        row.set_margin_start(14)
        row.set_margin_end(14)
        row.add_css_class("card")

        state = "Online" if node.online else "Offline"
        if not node.allowed and not is_router:
            state += " | Restricted"
        title = Gtk.Label(label=f"{node.label}  —  {state}", xalign=0)
        title.add_css_class("title-3" if is_router else "heading")
        row.append(title)

        details: list[str] = []
        if node.ip:
            details.append(f"IP: {node.ip}")
        if node.detail:
            details.append(node.detail)
        if not is_router:
            details.append(f"Type: {node.kind}")
        info = Gtk.Label(
            label="  |  ".join(details) or "No additional information",
            xalign=0,
            wrap=True,
        )
        info.add_css_class("dim-label")
        row.append(info)
        return row

    def cleanup(self) -> None:
        """Stop the periodic topology refresh when the window closes."""
        if self._refresh_source is not None:
            GLib.source_remove(self._refresh_source)
            self._refresh_source = None

    def dispose(self) -> None:
        if self._refresh_source is not None:
            GLib.source_remove(self._refresh_source)
            self._refresh_source = None
