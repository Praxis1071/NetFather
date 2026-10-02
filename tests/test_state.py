"""Shared GTK application state regression tests."""
from __future__ import annotations

import threading

from gui.state import ApplicationState


def test_subscribe_and_unsubscribe_are_safe() -> None:
    state = ApplicationState()
    calls: list[int] = []
    unsubscribe = state.subscribe(lambda: calls.append(1))

    state.notify_changed()
    unsubscribe()
    state.notify_changed()

    assert calls == [1]


def test_subscription_mutation_during_notification_does_not_corrupt_iteration() -> None:
    state = ApplicationState()
    calls: list[str] = []
    holder: dict[str, object] = {}

    def first() -> None:
        calls.append("first")
        unsubscribe = holder.get("unsubscribe")
        if callable(unsubscribe):
            unsubscribe()

    holder["unsubscribe"] = state.subscribe(first)
    state.subscribe(lambda: calls.append("second"))

    state.notify_changed()
    state.notify_changed()

    assert calls == ["first", "second", "second"]


def test_concurrent_subscribe_and_notify_are_safe() -> None:
    state = ApplicationState()
    errors: list[BaseException] = []
    stop = threading.Event()

    def notifier() -> None:
        try:
            while not stop.is_set():
                state.notify_changed()
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    thread = threading.Thread(target=notifier)
    thread.start()
    try:
        for _ in range(100):
            unsubscribe = state.subscribe(lambda: None)
            unsubscribe()
    finally:
        stop.set()
        thread.join(timeout=2)

    assert not errors
    assert not thread.is_alive()
