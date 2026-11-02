"""GTK4 application entry point for Linux."""
from __future__ import annotations

import sys
import threading

import gi

gi.require_version("Gdk", "4.0")
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk

from core.config import load_config
from core.i18n import set_language, tr
from gui.theme import ThemeController
from core.database import Database
from gui.state import ApplicationState
from gui.tasks import BackgroundTaskRunner
from gui.window import NetFatherWindow
from network.live_presence import LivePresenceService
from network.network_manager import NetworkManagerObserver


class NetFatherApplication(Adw.Application):
    """Own application-wide services while keeping pages view-focused."""

    def __init__(self) -> None:
        super().__init__(application_id="org.praxis1071.NetFather")
        self.config = None
        self.database = None
        self.state = ApplicationState()
        self.tasks = BackgroundTaskRunner()
        self.live_presence: LivePresenceService | None = None
        self.theme: ThemeController | None = None
        self._shutdown_complete = False
        self.network_manager = None
        self._unsubscribe_events = None
        self._presence_control_lock = threading.Lock()
        self._presence_request = 0
        self.connect("shutdown", self._on_shutdown)

    def _load_css(self) -> None:
        if self.theme is None:
            self.theme = ThemeController()
        self.theme.apply(self.config.ui.theme)

    def set_live_presence(self, enabled: bool) -> None:
        self._presence_request += 1
        request = self._presence_request
        def work():
            with self._presence_control_lock:
                if self._shutdown_complete or request != self._presence_request:
                    return
                if enabled:
                    self.live_presence.start()
                else:
                    self.live_presence.stop()
        def failed(error):
            if not self._shutdown_complete:
                self.state.network.status_message = tr("Operation failed: {error}", error=error)
                self.state.notify_changed()
        self.tasks.submit(work, lambda _: None, failed)

    def _on_live_reconciled(self, snapshot: object) -> None:
        def apply_state() -> bool:
            if self._shutdown_complete:
                return GLib.SOURCE_REMOVE
            self.state.discovery.scanned = getattr(snapshot, "scanned", 0)
            self.state.discovery.identities = getattr(snapshot, "identities", ())
            self.state.discovery.error = getattr(snapshot, "error", None)
            self.state.discovery.status_message = (
                tr('Live network update: {v0} new, {v1} updated, {v2} offline.', v0=getattr(snapshot, 'new_devices', 0), v1=getattr(snapshot, 'updated_devices', 0), v2=getattr(snapshot, 'offline_devices', 0))
            )
            self.state.notify_changed()
            return GLib.SOURCE_REMOVE

        GLib.idle_add(apply_state)

    def do_activate(self) -> None:
        if self.config is None:
            self.config = load_config()
            set_language(self.config.ui.language)
            self.state.discovery.status_message = tr("Ready")
            self.state.network.status_message = tr("Ready")
            self.database = Database(self.config.database_path)
            self.database.init_db()
            self._unsubscribe_events = self.database.events.subscribe(
                lambda _event: self.state.notify_changed(),
                dispatcher=lambda callback: GLib.idle_add(lambda: (callback(), GLib.SOURCE_REMOVE)[1]),
            )
            self.live_presence = LivePresenceService(
                self.database,
                interval_seconds=self.config.discovery.live_presence_interval_seconds,
                auto_register=self.config.discovery.auto_register,
                offline_after_seconds=self.config.discovery.offline_after_seconds,
                on_reconciled=self._on_live_reconciled,
            )
            if self.config.discovery.live_presence_enabled:
                self.live_presence.start()
            self.network_manager = NetworkManagerObserver(self.live_presence.request_reconcile)
            self.network_manager.start()

        self._load_css()
        window = self.props.active_window
        if window is None:
            window = NetFatherWindow(
                self,
                self.config,
                self.database,
                state=self.state,
                tasks=self.tasks,
            )
        window.present()

    def _on_shutdown(self, _application: Gtk.Application) -> None:
        """Release application-owned resources during GApplication shutdown."""
        if self._shutdown_complete:
            return
        self._shutdown_complete = True
        if self.network_manager is not None:
            self.network_manager.stop()
        if self._unsubscribe_events is not None:
            self._unsubscribe_events()
        if self.live_presence is not None:
            with self._presence_control_lock:
                self.live_presence.stop()
        self.tasks.shutdown()
        if self.theme is not None:
            self.theme.cleanup()
        if self.database is not None:
            self.database.close()


def main() -> int:
    return NetFatherApplication().run(sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
