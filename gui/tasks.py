"""Background task primitives for GTK4 pages.

Worker functions never receive GTK widgets. Results are delivered through a
GLib idle callback so UI mutation stays on the GTK main thread.
"""
from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor, CancelledError
import threading
from typing import Any

from gi.repository import GLib


class BackgroundTaskRunner:
    """Small process-wide worker pool for non-UI work."""

    def __init__(self, max_workers: int = 2) -> None:
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="netfather-worker",
        )
        self._closed = False

    def scope(self):
        return TaskScope(self)

    def submit(
        self,
        work: Callable[[], Any],
        on_success: Callable[[Any], None],
        on_error: Callable[[BaseException], None],
    ) -> Future[Any]:
        """Run *work* off the GTK thread and marshal its result to GTK."""
        if self._closed:
            raise RuntimeError("Background task runner is closed.")
        future = self._executor.submit(work)

        def complete(done: Future[Any]) -> None:
            if self._closed or done.cancelled():
                return
            try:
                result = done.result()
            except BaseException as exc:  # noqa: BLE001
                GLib.idle_add(self._deliver_error, on_error, exc)
            else:
                GLib.idle_add(self._deliver_success, on_success, result)

        future.add_done_callback(complete)
        return future

    @staticmethod
    def _deliver_success(callback: Callable[[Any], None], result: Any) -> bool:
        callback(result)
        return GLib.SOURCE_REMOVE

    @staticmethod
    def _deliver_error(callback: Callable[[BaseException], None], error: BaseException) -> bool:
        callback(error)
        return GLib.SOURCE_REMOVE

    def shutdown(self) -> None:
        """Stop accepting new work and wait for active workers."""
        self._closed = True
        self._executor.shutdown(wait=True, cancel_futures=True)


class TaskScope:
    """Page-owned delivery lifetime, independent of worker completion timing."""
    def __init__(self, runner: BackgroundTaskRunner) -> None:
        self.runner = runner
        self.closed = False
        self._lock = threading.RLock()
        self._futures: set[Future] = set()

    def submit(self, work, on_success, on_error):
        def deliver(callback, value):
            if not self.closed and not self.runner._closed:
                callback(value)
        with self._lock:
            if self.closed:
                return None
            future = self.runner.submit(work, lambda value: deliver(on_success, value),
                                        lambda error: deliver(on_error, error))
            self._futures.add(future)
            future.add_done_callback(self._discard)
            return future

    def _discard(self, future):
        with self._lock:
            self._futures.discard(future)

    def close(self):
        with self._lock:
            self.closed = True
            for future in tuple(self._futures):
                future.cancel()
            self._futures.clear()
