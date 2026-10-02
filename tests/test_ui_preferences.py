"""Persistence and theme decisions are independent of desktop availability."""
from __future__ import annotations

import pytest

import core.config as config_module
from core.appearance import prefers_dark
from core.exceptions import ConfigError


@pytest.fixture
def config_path(tmp_path, monkeypatch):
    monkeypatch.setattr(config_module, "DEFAULT_DATA_DIR", tmp_path / "data")
    return tmp_path / "config.toml"


def test_ui_defaults_and_legacy_configuration(config_path):
    created = config_module.load_config(config_path)
    assert created.ui.theme == created.ui.language == "system"
    config_path.write_text(f'[general]\ndata_dir = "{created.data_dir}"\n[discovery]\nmode = "passive"\n')
    legacy = config_module.load_config(config_path)
    assert legacy.ui.theme == legacy.ui.language == "system"
    assert legacy.discovery.mode == "passive"


@pytest.mark.parametrize("theme,language", [("light", "en"), ("dark", "tr"), ("system", "az")])
def test_preferences_survive_restart_without_resetting_network_config(config_path, theme, language):
    config = config_module.load_config(config_path)
    config.ui.theme = theme
    config.ui.language = language
    config.discovery.mode = "passive"
    config.discovery.offline_after_seconds = 120
    config.firewall.enforcement_topology = "gateway"
    config_module.save_config(config)
    loaded = config_module.load_config(config_path)
    assert loaded.ui.theme == theme and loaded.ui.language == language
    assert loaded.discovery.mode == "passive"
    assert loaded.discovery.offline_after_seconds == 120
    assert loaded.firewall.enforcement_topology == "gateway"


@pytest.mark.parametrize("field,value", [("theme", "neon"), ("language", "de")])
def test_invalid_preferences_report_configuration_error(config_path, field, value):
    config_path.write_text(f'[ui]\n{field} = "{value}"\n')
    with pytest.raises(ConfigError, match=f"ui.{field}"):
        config_module.load_config(config_path)


@pytest.mark.parametrize("theme,system_dark,expected", [
    ("system", False, False), ("system", True, True),
    ("light", False, False), ("light", True, False),
    ("dark", False, True), ("dark", True, True),
])
def test_explicit_theme_and_system_following(theme, system_dark, expected):
    assert prefers_dark(theme, system_dark) is expected


def test_invalid_theme_is_not_silently_applied():
    with pytest.raises(ValueError):
        prefers_dark("neon", True)
