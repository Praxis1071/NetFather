"""Small UI translation service, independent of GTK and network operations."""
from __future__ import annotations

import json
import os
from functools import lru_cache
from importlib.resources import files
from typing import Mapping

LANGUAGES = ("system", "en", "tr", "az")
LANGUAGE_NAMES = {"en": "English", "tr": "Türkçe", "az": "Azərbaycanca"}
_language = "en"


def resolve_language(preference: str, environment: Mapping[str, str] | None = None) -> str:
    if preference not in LANGUAGES:
        raise ValueError(f"Unsupported language: {preference}")
    if preference != "system":
        return preference
    env = os.environ if environment is None else environment
    # LANGUAGE is a gettext priority list; LC_ALL/LC_MESSAGES precede LANG.
    candidates = env.get("LANGUAGE", "").split(":")
    candidates.append(env.get("LC_ALL") or env.get("LC_MESSAGES") or env.get("LANG", ""))
    for candidate in candidates:
        code = candidate.split(".", 1)[0].split("_", 1)[0].split("-", 1)[0].lower()
        if code in LANGUAGE_NAMES:
            return code
    return "en"


@lru_cache(maxsize=3)
def catalog(language: str) -> dict[str, str]:
    if language not in LANGUAGE_NAMES:
        raise ValueError(f"Unsupported catalog: {language}")
    resource = files("core").joinpath("locales", f"{language}.json")
    return json.loads(resource.read_text(encoding="utf-8"))


def set_language(preference: str) -> str:
    global _language
    language = resolve_language(preference)
    catalog(language)  # Validate availability before changing runtime state.
    _language = language
    return language


def get_language() -> str:
    return _language


def tr(message: str, **values: object) -> str:
    """Translate a message template; interpolate values only after lookup."""
    template = catalog(_language).get(message, message)
    return template.format(**values) if values else template
