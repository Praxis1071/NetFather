from __future__ import annotations

import io
from types import SimpleNamespace

from rich.console import Console

import cli.output as output


def test_windows_redirected_output_is_normalized_to_utf8(monkeypatch) -> None:
    raw = io.BytesIO()
    stream = io.TextIOWrapper(raw, encoding="cp1252", errors="strict")
    monkeypatch.setattr(output, "os", SimpleNamespace(name="nt"))

    configured = output._configure_output_stream(stream)

    assert configured.encoding.lower().replace("-", "") == "utf8"
    assert configured.errors == "replace"

    console = Console(file=configured, force_terminal=False, color_system=None)
    table = output.make_table("Alan", "Değer")
    table.add_row("OS", "Windows")
    console.print(table)
    configured.flush()
    assert "Değer".encode("utf-8") in raw.getvalue()
