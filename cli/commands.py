"""
NetFather CLI komutları.

Komut yapısı:

    netfather status
    netfather scan
    netfather config
    netfather device list
    netfather device info <name>
    netfather device add
    netfather device remove <name>
    netfather rules list
    netfather rules create
    netfather monitor

FAZ 1'de yalnızca; status, config ve device (list/info/add/remove)
komutları tam işlevseldir. scan, rules ve monitor komutları ilerideki
fazlarda uygulanacak olan yer tutuculardır.
"""

from __future__ import annotations

from typing import Optional

import typer

from cli.output import (
    console,
    make_table,
    print_error,
    print_info,
    print_success,
    print_title,
    print_warning,
)
from core.config import Config, load_config
from core.database import Database, get_database
from core.exceptions import DeviceNotFoundError, NetFatherError
from core.logger import get_logger, setup_logging
from manager.device_manager import DeviceManager
from network.interface import get_network_status

log = get_logger("cli")

app = typer.Typer(
    name="netfather",
    help="NetFather - Yerel ağ cihaz ve erişim yönetim aracı.",
    no_args_is_help=True,
    add_completion=True,
)

device_app = typer.Typer(help="Cihaz kayıtlarını yönetir.", no_args_is_help=True)
rules_app = typer.Typer(help="Cihaz bazlı erişim kurallarını yönetir.", no_args_is_help=True)

app.add_typer(device_app, name="device")
app.add_typer(rules_app, name="rules")

_state: dict[str, Config | Database] = {}


def _bootstrap() -> tuple[Config, Database]:
    """Config'i yükler, logging'i kurar ve database bağlantısını hazırlar."""
    if "config" in _state and "db" in _state:
        return _state["config"], _state["db"]  # type: ignore[return-value]

    config = load_config()
    setup_logging(config)
    db = get_database(config.database_path)

    _state["config"] = config
    _state["db"] = db
    return config, db


@app.callback()
def main_callback() -> None:
    """NetFather - Yerel ağ cihaz ve erişim yönetim aracı."""
    # Her komuttan önce config/db/logging hazırlanır.
    _bootstrap()


@app.command()
def status() -> None:
    """Aktif ağ arayüzü ve genel sistem durumunu gösterir."""
    config, _ = _bootstrap()
    print_title("Network Status")

    net = get_network_status()

    table = make_table("Alan", "Değer")
    table.add_row("Interface", net.interface or "[dim]tespit edilemedi (FAZ 2)[/dim]")
    table.add_row("IP", net.local_ip or "[dim]tespit edilemedi (FAZ 2)[/dim]")
    table.add_row("Gateway", net.gateway or "[dim]tespit edilemedi (FAZ 2)[/dim]")
    table.add_row("Config", str(config.config_path))
    table.add_row("Database", str(config.database_path))
    console.print(table)


@app.command()
def scan() -> None:
    """Yerel ağı tarayıp cihazları keşfeder. (FAZ 3'te uygulanacak)"""
    print_warning("Ağ tarama özelliği henüz aktif değil. Bu özellik FAZ 3'te eklenecektir.")


@app.command()
def monitor() -> None:
    """Canlı cihaz durumu ekranını açar. (FAZ 6'da uygulanacak)"""
    print_warning("Canlı monitoring özelliği henüz aktif değil. Bu özellik FAZ 6'da eklenecektir.")


@app.command()
def config(
    show_path: bool = typer.Option(
        False, "--path", help="Sadece config dosyasının yolunu yazdırır."
    )
) -> None:
    """Aktif config dosyasının içeriğini ve yolunu gösterir."""
    cfg, _ = _bootstrap()

    if show_path:
        console.print(str(cfg.config_path))
        return

    print_title("Config")
    table = make_table("Ayar", "Değer")
    table.add_row("Config dosyası", str(cfg.config_path))
    table.add_row("Data dizini", str(cfg.data_dir))
    table.add_row("Database", str(cfg.database_path))
    table.add_row("Log dosyası", str(cfg.log_path))
    table.add_row("Log seviyesi", cfg.logging.level)
    console.print(table)


# ---------------------------------------------------------------------------
# device alt komutları
# ---------------------------------------------------------------------------


@device_app.command("list")
def device_list() -> None:
    """Kayıtlı tüm cihazları listeler."""
    _, db = _bootstrap()
    manager = DeviceManager(db)
    devices = manager.list_devices()

    if not devices:
        print_info("Henüz kayıtlı cihaz yok. 'netfather device add' ile ekleyebilirsiniz.")
        return

    table = make_table("ID", "İsim", "MAC", "IP", "Tip", "Son Görülme", title="Kayıtlı Cihazlar")
    for d in devices:
        table.add_row(
            str(d.id),
            d.name,
            d.mac,
            d.ip or "-",
            d.device_type,
            d.last_seen.strftime("%Y-%m-%d %H:%M") if d.last_seen else "-",
        )
    console.print(table)


@device_app.command("info")
def device_info(name: str = typer.Argument(..., help="Cihaz ismi")) -> None:
    """Belirtilen cihazın detaylarını gösterir."""
    _, db = _bootstrap()
    manager = DeviceManager(db)
    try:
        d = manager.get_device_by_name(name)
    except DeviceNotFoundError as exc:
        print_error(str(exc))
        raise typer.Exit(code=1) from exc

    print_title(f"Device: {d.name}")
    table = make_table("Alan", "Değer")
    table.add_row("ID", str(d.id))
    table.add_row("İsim", d.name)
    table.add_row("MAC", d.mac)
    table.add_row("IP", d.ip or "-")
    table.add_row("Üretici", d.vendor or "-")
    table.add_row("Tip", d.device_type)
    table.add_row("Kayıt Tarihi", d.created_at.strftime("%Y-%m-%d %H:%M"))
    table.add_row(
        "Son Görülme", d.last_seen.strftime("%Y-%m-%d %H:%M") if d.last_seen else "-"
    )
    console.print(table)


@device_app.command("add")
def device_add(
    name: str = typer.Option(..., "--name", "-n", prompt=True, help="Cihaz ismi"),
    mac: str = typer.Option(..., "--mac", "-m", prompt=True, help="MAC adresi (AA:BB:CC:DD:EE:FF)"),
    ip: Optional[str] = typer.Option(None, "--ip", help="IP adresi"),
    device_type: str = typer.Option(
        "unknown", "--type", "-t", help="Cihaz tipi (laptop, phone, tablet, iot, vb.)"
    ),
) -> None:
    """Yeni bir cihazı elle kaydeder."""
    _, db = _bootstrap()
    manager = DeviceManager(db)

    try:
        device = manager.add_device(name=name, mac=mac, ip=ip, device_type=device_type)
    except NetFatherError as exc:
        print_error(f"Cihaz eklenemedi: {exc}")
        raise typer.Exit(code=1) from exc

    print_success(f"Cihaz eklendi: {device.name} ({device.mac})")


@device_app.command("remove")
def device_remove(name: str = typer.Argument(..., help="Silinecek cihaz ismi")) -> None:
    """Kayıtlı bir cihazı siler."""
    _, db = _bootstrap()
    manager = DeviceManager(db)
    try:
        manager.delete_device(name)
    except DeviceNotFoundError as exc:
        print_error(str(exc))
        raise typer.Exit(code=1) from exc

    print_success(f"Cihaz silindi: {name}")


# ---------------------------------------------------------------------------
# rules alt komutları (FAZ 5'te tamamlanacak)
# ---------------------------------------------------------------------------


@rules_app.command("list")
def rules_list() -> None:
    """Tanımlı kuralları listeler. (FAZ 5'te uygulanacak)"""
    print_warning("Kural sistemi henüz aktif değil. Bu özellik FAZ 5'te eklenecektir.")


@rules_app.command("create")
def rules_create() -> None:
    """Yeni bir erişim kuralı oluşturur. (FAZ 5'te uygulanacak)"""
    print_warning("Kural sistemi henüz aktif değil. Bu özellik FAZ 5'te eklenecektir.")
