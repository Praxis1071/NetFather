"""Execute production preference callbacks; rendering requires GTK runtime QA."""
from __future__ import annotations

import ast
import __future__
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.config import Config, save_config, load_config
from core.i18n import get_language, set_language, tr

GUI = Path(__file__).resolve().parents[1] / "gui"


def callback(filename, parent, name, environment):
    """Retain the original nested callback and its nonlocal guard."""
    tree = ast.parse((GUI / filename).read_text())
    method = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == parent)
    nested = next(node for node in method.body if isinstance(node, ast.FunctionDef) and node.name == name)
    wrapper = ast.parse(f"def make():\n    updating = False\n    return {name}\n").body[0]
    wrapper.body.insert(1, nested)
    module = ast.fix_missing_locations(ast.Module(body=[wrapper], type_ignores=[]))
    namespace = {"tr": tr, "save_config": save_config, **environment}
    exec(compile(module, filename, "exec", flags=__future__.annotations.compiler_flag), namespace)
    return namespace["make"]()


@pytest.fixture
def preferences(tmp_path):
    previous_language = get_language()
    set_language("en")
    config = Config(config_path=tmp_path / "config.toml")
    config.general.data_dir = str(tmp_path / "data")
    config.discovery.live_presence_enabled = False
    save_config(config)
    status = SimpleNamespace(set_text=lambda text: setattr(status, "text", text))
    applied = []
    app = SimpleNamespace(theme=SimpleNamespace(apply=applied.append))
    yield config, status, app, applied
    set_language(previous_language)


def test_theme_callback_persists_and_applies_immediately(preferences):
    config, status, app, applied = preferences
    changed = callback("settings_page.py", "_appearance_card", "changed", {
        "self": SimpleNamespace(app=app), "config": config, "status": status,
    })
    changed(SimpleNamespace(get_active_id=lambda: "dark"), "theme")
    assert load_config(config.config_path).ui.theme == "dark"
    assert applied == ["dark"]


def test_language_callback_saves_without_invalidating_current_forms(preferences):
    config, status, app, applied = preferences
    changed = callback("settings_page.py", "_appearance_card", "changed", {
        "self": SimpleNamespace(app=app), "config": config, "status": status,
    })
    changed(SimpleNamespace(get_active_id=lambda: "tr"), "language")
    assert load_config(config.config_path).ui.language == "tr"
    assert get_language() == "en" and not applied
    assert "Restart" in status.text


def test_save_failure_restores_selection_without_applying_theme(preferences):
    config, status, app, applied = preferences
    def fail(_config):
        raise OSError("read-only directory")
    changed = callback("settings_page.py", "_appearance_card", "changed", {
        "self": SimpleNamespace(app=app), "config": config, "status": status, "save_config": fail,
    })
    selection = {"value": "dark"}
    def reset(value):
        selection["value"] = value
        changed(combo, "theme")  # A real ComboBox emits changed on reset.
    combo = SimpleNamespace(get_active_id=lambda: selection["value"], set_active_id=reset)
    changed(combo, "theme")
    assert config.ui.theme == selection["value"] == "system"
    assert load_config(config.config_path).ui.theme == "system"
    assert not applied and "read-only directory" in status.text


def test_live_switch_reads_new_state_and_persists_before_starting_service(preferences):
    config, status, app, _ = preferences
    calls = []
    service = SimpleNamespace(start=lambda: calls.append("start"), stop=lambda: calls.append("stop"))
    app.live_presence = service
    enabled = SimpleNamespace(active=True)
    enabled.get_active = lambda: enabled.active
    apply = callback("settings_page.py", "_live_presence_card", "apply_settings", {
        "self": SimpleNamespace(app=app), "config": config, "status": status,
        "enabled": enabled, "interval": SimpleNamespace(get_value=lambda: 12),
    })
    apply(enabled)
    assert load_config(config.config_path).discovery.live_presence_enabled
    assert service.interval_seconds == 12 and calls == ["start"]
    enabled.active = False
    apply(enabled)
    assert not load_config(config.config_path).discovery.live_presence_enabled
    assert calls == ["start", "stop"]


def test_live_preference_save_failure_restores_controls_and_keeps_service_unchanged(preferences):
    config, status, app, _ = preferences
    calls = []
    app.live_presence = SimpleNamespace(start=lambda: calls.append("start"), stop=lambda: calls.append("stop"))
    enabled = SimpleNamespace(active=True)
    enabled.get_active = lambda: enabled.active
    enabled.set_active = lambda value: setattr(enabled, "active", value)
    interval = SimpleNamespace(value=12)
    interval.get_value = lambda: interval.value
    interval.set_value = lambda value: setattr(interval, "value", value)
    def fail(_config):
        raise OSError("read-only directory")
    apply = callback("settings_page.py", "_live_presence_card", "apply_settings", {
        "self": SimpleNamespace(app=app), "config": config, "status": status,
        "enabled": enabled, "interval": interval, "save_config": fail,
    })
    apply(enabled)
    loaded = load_config(config.config_path)
    assert not enabled.active and not config.discovery.live_presence_enabled
    assert interval.value == config.discovery.live_presence_interval_seconds == loaded.discovery.live_presence_interval_seconds
    assert not calls and "read-only directory" in status.text


@pytest.mark.parametrize("language", ["en", "tr", "az"])
def test_pause_state_survives_translated_or_arbitrary_button_label(language):
    previous = get_language()
    try:
        set_language(language)
        tree = ast.parse((GUI / "monitoring_page.py").read_text())
        method = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == "_toggle_pause")
        namespace = {"tr": tr}
        exec(compile(ast.Module(body=[method], type_ignores=[]), "monitoring_page.py", "exec",
                     flags=__future__.annotations.compiler_flag), namespace)
        labels = []
        page = SimpleNamespace(_paused=False, pause_button=SimpleNamespace(set_label=labels.append),
                               live_label=SimpleNamespace(set_text=lambda _text: None))
        namespace["_toggle_pause"](page, None)
        assert page._paused and labels[-1] == tr("Resume live refresh")
        namespace["_toggle_pause"](page, None)
        assert not page._paused and labels[-1] == tr("Pause live refresh")
    finally:
        set_language(previous)
