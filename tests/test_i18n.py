"""Locale selection and translation-resource contracts without GTK."""
from __future__ import annotations

import ast
from pathlib import Path
from string import Formatter

import pytest

from core.i18n import catalog, get_language, resolve_language, set_language, tr


@pytest.fixture(autouse=True)
def restore_language():
    previous = get_language()
    yield
    set_language(previous)


@pytest.mark.parametrize("environment,expected", [
    ({"LANG": "tr_TR.UTF-8"}, "tr"),
    ({"LANG": "az-AZ"}, "az"),
    ({"LANG": "de_DE.UTF-8"}, "en"),
    ({}, "en"),
    ({"LANGUAGE": "de:az:tr", "LC_ALL": "en_US.UTF-8"}, "az"),
    ({"LC_ALL": "tr_TR", "LC_MESSAGES": "az_AZ", "LANG": "en_US"}, "tr"),
    ({"LC_MESSAGES": "az_AZ", "LANG": "tr_TR"}, "az"),
    ({"LC_ALL": "de_DE", "LANG": "tr_TR"}, "en"),
])
def test_system_locale_selection(environment, expected):
    assert resolve_language("system", environment) == expected


@pytest.mark.parametrize("language", ["en", "tr", "az"])
def test_explicit_language_overrides_system(language):
    assert resolve_language(language, {"LANGUAGE": "de", "LANG": "en_US"}) == language


def test_unsupported_selection_leaves_current_language_intact():
    set_language("tr")
    with pytest.raises(ValueError):
        set_language("de")
    assert get_language() == "tr"


@pytest.mark.parametrize("language,ready", [("en", "Ready"), ("tr", "Hazır"), ("az", "Hazır")])
def test_lookup_interpolation_and_unknown_diagnostic_fallback(language, ready):
    set_language(language)
    assert tr("Ready") == ready
    assert "0.5.0" in tr("Version {version}", version="0.5.0")
    assert tr("unrecognized backend diagnostic") == "unrecognized backend diagnostic"


def placeholders(message):
    return sorted((name, spec, conversion) for _, name, spec, conversion in Formatter().parse(message) if name is not None)


@pytest.mark.parametrize("language", ["en", "tr", "az"])
def test_catalogs_preserve_every_key_and_format_specification(language):
    english = catalog("en")
    translated = catalog(language)
    assert translated.keys() == english.keys()
    for source, value in translated.items():
        assert isinstance(value, str) and value.strip(), source
        assert placeholders(source) == placeholders(value), source


def test_literal_ui_messages_are_present_in_all_catalogs():
    root = Path(__file__).resolve().parents[1]
    messages = set()
    for path in (root / "gui").glob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "tr":
                if node.args and isinstance(node.args[0], ast.Constant):
                    messages.add(node.args[0].value)
    for language in ("en", "tr", "az"):
        assert not messages - catalog(language).keys()


@pytest.mark.parametrize("language", ["tr", "az"])
def test_about_and_navigation_have_translations(language):
    set_language(language)
    for message in ("About", "Contributors", "Cavanşir's GitHub profile", "Settings",
                    "Local-network discovery, monitoring, profiles, scheduling and access management for Linux."):
        assert tr(message) != message
