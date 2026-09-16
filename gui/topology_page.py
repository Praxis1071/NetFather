"""GTK4 network topology workspace."""
from __future__ import annotations

from gi.repository import Gtk

from gui.tasks import BackgroundTaskRunner
from network.topology import NetworkTopology, TopologyNode, build_topology
from core.database import Database


class TopologyPage(Gtk.Box):
    """Render the backend topology as a clean vertical network view."""

    def __init__(self, database: Database, tasks: BackgroundTaskRunner) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self.set_margin_top(28)
        self.set_margin_bottom(28)
        self.set_margin_start(32)
        self.set_margin_end(32)
        self.database = database
        self.tasks = tasks
        self._busy = False

        heading = Gtk.Label(label="Network Topology", xalign=0)
        heading.add_css_class("title-1")
        self.append(heading)
        subtitle = Gtk.Label(
            label="Live logical view of the gateway and registered local-network devices.",
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
        online = sum(1 for node in topology.nodes if node.kind != "router" and node.online)
        devices = sum(1 for node in topology.nodes if node.kind != "router")
        self.summary.set_text(f"{devices} devices | {online} online")
        self.status.set_text("Topology refreshed.")

    def _refresh_failed(self, error: BaseException) -> None:
        self._busy = False
        self.refresh_button.set_sensitive(True)
        self.status.set_text(str(error))

    def _render(self, topology: NetworkTopology) -> None:
        while (child := self.list_box.get_first_child()) is not None:
            self.list_box.remove(child)

        if not topology.nodes:
            self.list_box.append(Gtk.Label(label="No topology data available.", xalign=0))
            return

        router = next((node for node in topology.nodes if node.kind == "router"), None)
        if router is not None:
            self.list_box.append(self._node_row(router, is_router=True))

        for node in topology.nodes:
            if node.kind == "router":
                continue
            connector = Gtk.Label(label="│", xalign=0)
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

        state = "Online" if node.online else "Offline"
        if not node.allowed:
            state += " | Restricted"
        title = Gtk.Label(label=f"{node.label}  —  {state}", xalign=0)
        title.add_css_class("title-3" if is_router else "heading")
        row.append(title)

        details = []
        if node.ip:
            details.append(f"IP: {node.ip}")
        if node.detail:
            details.append(node.detail)
        if not is_router:
            details.append(f"Type: {node.kind}")
        info = Gtk.Label(label="  |  ".join(details) or "No additional information", xalign=0, wrap=True)
        info.add_css_class("dim-label")
        row.append(info)
        return row
