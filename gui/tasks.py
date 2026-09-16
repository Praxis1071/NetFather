"""Background task primitives for GTK4 pages.

Worker functions never receive GTK widgets. Results are delivered through a
GLib idle callback so UI mutation stays on the GTK main thread.
"""
from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any

from gi.repository import GLib


class BackgroundTaskRunner:
    """Small process-wide worker pool for non-UI work."""

    def __init__(self, max_workers: int = 2) -> None:
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="netfather-worker",
        )

    def submit(
        self,
        work: Callable[[], Any],
        on_success: Callable[[Any], None],
        on_error: Callable[[BaseException], None],
    ) -> Future[Any]:
        """Run *work* off the GTK thread and marshal its result to GTK."""
        future = self._executor.submit(work)

        def complete(done: Future[Any]) -> None:
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
        self._executor.shutdown(wait=True, cancel_futures=True)
