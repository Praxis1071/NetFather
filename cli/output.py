"""
Rich tabanlı ortak CLI çıktı yardımcıları.

Tüm komutlar tutarlı bir görsel dil kullanabilsin diye başlık, tablo ve
durum mesajı fonksiyonları burada toplanır.

Unix CLI kuralına uygun olarak normal çıktı stdout'a (``console``), hata ve
uyarı mesajları ise stderr'e (``err_console``) yazılır. Bu ayrım, çıktının
`netfather device list > devices.txt` gibi yönlendirmelerde (redirection)
hata mesajlarıyla karışmamasını sağlar.
"""

from __future__ import annotations

import os
import sys
from typing import TextIO

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

def _configure_output_stream(stream: TextIO) -> TextIO:
    """Make CLI output robust on Windows consoles and redirected CI streams.

    Windows runners (and some redirected Windows terminals) may expose a legacy
    code page such as cp1252. NetFather's UI contains Turkish text and Rich
    renderables, so strict encoding can raise ``UnicodeEncodeError`` while
    merely printing a table. Redirected output is safe to normalize to UTF-8;
    interactive consoles keep their native encoding but replace unsupported
    glyphs rather than terminating the command.
    """
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is None:
        return stream
    try:
        is_tty = bool(stream.isatty())
    except (AttributeError, OSError):
        is_tty = False
    try:
        if os.name == "nt" and not is_tty:
            reconfigure(encoding="utf-8", errors="replace")
        else:
            reconfigure(errors="replace")
    except (AttributeError, OSError, ValueError):
        pass
    return stream


console = Console(file=_configure_output_stream(sys.stdout))
err_console = Console(file=_configure_output_stream(sys.stderr), stderr=True)

APP_BRAND = "NetFather"


def print_title(subtitle: str) -> None:
    """Standart bir başlık paneli basar, ör: 'NetFather Network Status'."""
    console.print(Panel.fit(f"[bold cyan]{APP_BRAND}[/bold cyan] {subtitle}"))


def print_success(message: str) -> None:
    """Başarı mesajını stdout'a basar."""
    console.print(f"[bold green]✓[/bold green] {message}")


def print_error(message: str) -> None:
    """Hata mesajını stderr'e basar."""
    err_console.print(f"[bold red]✗[/bold red] {message}")


def print_warning(message: str) -> None:
    """Uyarı mesajını stderr'e basar."""
    err_console.print(f"[bold yellow]![/bold yellow] {message}")


def print_info(message: str) -> None:
    """Bilgi mesajını stdout'a basar."""
    console.print(f"[cyan]i[/cyan] {message}")


def make_table(*columns: str, title: str | None = None) -> Table:
    """Standart stilde boş bir Rich tablo oluşturur."""
    table = Table(title=title, header_style="bold cyan", show_lines=False)
    for col in columns:
        table.add_column(col)
    return table
