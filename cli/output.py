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

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()
err_console = Console(stderr=True)

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
