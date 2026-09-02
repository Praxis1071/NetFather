"""Network-device helper functions.

The module deliberately performs vendor lookup from a *local* OUI database.
NetFather never sends a device MAC address to a remote lookup service.
"""

from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path

_MAC_PATTERN = re.compile(r"^(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}$")
_HEX_OUI_LINE = re.compile(
    r"^\s*([0-9A-Fa-f]{2})[-:]([0-9A-Fa-f]{2})[-:]([0-9A-Fa-f]{2})\s+\(hex\)\s+(.+?)\s*$"
)
_BASE16_OUI_LINE = re.compile(r"^\s*([0-9A-Fa-f]{6})\s+\(base 16\)\s+(.+?)\s*$")
_WIRESHARK_OUI_LINE = re.compile(
    r"^\s*([0-9A-Fa-f]{2})[:-]([0-9A-Fa-f]{2})[:-]([0-9A-Fa-f]{2})\s+([^#\t].*?)\s*$"
)

_DEFAULT_OUI_PATHS = (
    Path("/usr/share/ieee-data/oui.txt"),
    Path("/usr/share/hwdata/oui.txt"),
    Path("/usr/share/misc/oui.txt"),
    Path("/var/lib/ieee-data/oui.txt"),
    Path("/usr/share/wireshark/manuf"),
)


def normalize_mac(mac: str) -> str:
    """Validate and normalize a MAC address to ``AA:BB:CC:DD:EE:FF``."""
    if not isinstance(mac, str):
        raise TypeError("MAC address must be a string")
    candidate = mac.strip()
    if not _MAC_PATTERN.fullmatch(candidate):
        raise ValueError(f"Invalid MAC address format: {mac!r}")
    return candidate.upper().replace("-", ":")


def find_oui_database() -> Path | None:
    """Return the first readable local OUI database path, if one is available."""
    override = os.environ.get("NETFATHER_OUI_FILE")
    candidates = (Path(override).expanduser(),) if override else _DEFAULT_OUI_PATHS
    for path in candidates:
        try:
            if path.is_file() and os.access(path, os.R_OK):
                return path
        except OSError:
            continue
    return None


def _clean_vendor(value: str) -> str:
    value = value.strip().strip('"')
    # Wireshark's manuf file may append a longer descriptive name after a tab.
    return value.split("\t", 1)[0].strip()


@lru_cache(maxsize=4)
def _load_oui_database(path_text: str) -> dict[str, str]:
    """Load a supported local OUI file into a ``prefix -> vendor`` mapping."""
    path = Path(path_text)
    vendors: dict[str, str] = {}
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for raw_line in handle:
                if not raw_line.strip() or raw_line.lstrip().startswith("#"):
                    continue

                match = _HEX_OUI_LINE.match(raw_line)
                if match:
                    prefix = "".join(match.group(i).upper() for i in (1, 2, 3))
                    vendors.setdefault(prefix, _clean_vendor(match.group(4)))
                    continue

                match = _BASE16_OUI_LINE.match(raw_line)
                if match:
                    vendors.setdefault(match.group(1).upper(), _clean_vendor(match.group(2)))
                    continue

                # Wireshark ``manuf`` format. Only accept exact 24-bit prefixes;
                # variable masks are intentionally ignored here.
                if "/" not in raw_line.split(maxsplit=1)[0]:
                    match = _WIRESHARK_OUI_LINE.match(raw_line)
                    if match:
                        prefix = "".join(match.group(i).upper() for i in (1, 2, 3))
                        vendors.setdefault(prefix, _clean_vendor(match.group(4)))
    except OSError:
        return {}
    return vendors


def lookup_vendor(mac: str) -> str | None:
    """Return a vendor name from a local OUI database, without network access."""
    try:
        normalized = normalize_mac(mac)
    except (TypeError, ValueError):
        return None

    path = find_oui_database()
    if path is None:
        return None

    prefix = normalized.replace(":", "")[:6]
    return _load_oui_database(str(path)).get(prefix)


def clear_oui_cache() -> None:
    """Clear the in-memory OUI cache. Primarily useful for tests."""
    _load_oui_database.cache_clear()
