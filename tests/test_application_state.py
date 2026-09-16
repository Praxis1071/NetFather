from network.identity import DeviceIdentity
from gui.state import ApplicationState


def test_application_state_contains_discovery_state() -> None:
    state = ApplicationState()
    assert state.discovery.mode == "hybrid"
    assert state.discovery.running is False
    assert state.discovery.identities == ()


def test_application_state_notifies_listeners() -> None:
    state = ApplicationState()
    changes: list[bool] = []
    unsubscribe = state.subscribe(lambda: changes.append(True))

    state.discovery.running = True
    state.notify_changed()
    unsubscribe()
    state.notify_changed()

    assert changes == [True]
