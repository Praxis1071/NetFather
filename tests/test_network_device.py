from __future__ import annotations

from pathlib import Path

import pytest

from network.device import clear_oui_cache, find_oui_database, lookup_vendor, normalize_mac


def test_normalize_mac_validates_and_normalizes() -> None:
    assert normalize_mac("aa-bb-cc-dd-ee-ff") == "AA:BB:CC:DD:EE:FF"
    with pytest.raises(ValueError):
        normalize_mac("bad")


def test_lookup_vendor_uses_local_oui_file(tmp_path: Path, monkeypatch) -> None:
    oui = tmp_path / "oui.txt"
    oui.write_text("AA-BB-CC   (hex)        Example Networks Inc.\n", encoding="utf-8")
    monkeypatch.setenv("NETFATHER_OUI_FILE", str(oui))
    clear_oui_cache()
    try:
        assert find_oui_database() == oui
        assert lookup_vendor("AA:BB:CC:00:11:22") == "Example Networks Inc."
        assert lookup_vendor("11:22:33:44:55:66") is None
    finally:
        clear_oui_cache()


def test_lookup_vendor_invalid_mac_returns_none() -> None:
    assert lookup_vendor("not-a-mac") is None
