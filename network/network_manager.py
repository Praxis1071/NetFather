"""Optional libnm signal adapter, owned by the application's GLib context."""
from __future__ import annotations

from core.logger import get_logger
log = get_logger("network_manager")


class NetworkManagerObserver:
    def __init__(self, on_changed) -> None:
        self.on_changed = on_changed
        self.client = None
        self._handlers: list[tuple[object, int]] = []
        self.warning: str | None = None

    def _connect(self, obj, signal, callback):
        self._handlers.append((obj, obj.connect(signal, callback)))

    def _device(self, _client, device):
        self._connect(device, "state-changed", self._changed)
        self._connect(device, "notify::active-connection", self._changed)
        self._connect(device, "notify::ip4-config", self._changed)
        self._connect(device, "notify::ip6-config", self._changed)
        self._changed()

    def _changed(self, *_args):
        try:
            self.on_changed()
        except Exception:
            log.exception("NetworkManager state consumer failed")

    def start(self) -> bool:
        if self.client is not None:
            return True
        try:
            import gi
            gi.require_version("NM", "1.0")
            from gi.repository import NM
            self.client = NM.Client.new(None)
            if not self.client.get_nm_running():
                raise RuntimeError("NetworkManager service is unavailable")
            self._connect(self.client, "device-added", self._device)
            self._connect(self.client, "device-removed", self._changed)
            self._connect(self.client, "notify::active-connections", self._changed)
            for device in self.client.get_devices():
                self._device(self.client, device)
            return True
        except (ImportError, ValueError, RuntimeError) as exc:
            self.warning = f"NetworkManager signals unavailable; periodic discovery continues: {exc}"
            self.stop()
            return False

    def stop(self) -> None:
        for obj, handler in self._handlers:
            obj.disconnect(handler)
        self._handlers.clear()
        self.client = None
