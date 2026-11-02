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
        self._generation = 0
        self._starting = False
        self._cancellable = None

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
        if self.client is not None or self._starting:
            return True
        try:
            import gi
            gi.require_version("NM", "1.0")
            from gi.repository import Gio, NM
            self._generation += 1
            generation = self._generation
            self._starting = True
            self._cancellable = Gio.Cancellable()
            def ready(_source, result, *_data):
                try:
                    client = NM.Client.new_finish(result)
                    if generation != self._generation:
                        return
                    self._starting = False
                    if not client.get_nm_running():
                        raise RuntimeError("NetworkManager service is unavailable")
                    self.client = client
                    self._connect(client, "device-added", self._device)
                    self._connect(client, "device-removed", self._removed)
                    self._connect(client, "notify::active-connections", self._changed)
                    for device in client.get_devices():
                        self._device(client, device)
                except Exception as exc:
                    if generation == self._generation:
                        self.warning = f"NetworkManager signals unavailable; periodic discovery continues: {exc}"
                        self.stop()
            NM.Client.new_async(self._cancellable, ready, None)
            return True
        except Exception as exc:
            self.warning = f"NetworkManager signals unavailable; periodic discovery continues: {exc}"
            self.stop()
            return False

    def stop(self) -> None:
        self._generation += 1
        self._starting = False
        if self._cancellable is not None:
            self._cancellable.cancel()
            self._cancellable = None
        for obj, handler in self._handlers:
            obj.disconnect(handler)
        self._handlers.clear()
        self.client = None

    def _removed(self, _client, device):
        for obj, handler in tuple(self._handlers):
            if obj is device:
                obj.disconnect(handler)
                self._handlers.remove((obj, handler))
        self._changed()
