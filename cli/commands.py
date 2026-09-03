"""NetFather command-line interface.

The CLI and the TUI intentionally share the same managers and network layer;
there is no second implementation of device/profile/rule logic in the UI.
"""

from __future__ import annotations

import sys
from importlib.metadata import PackageNotFoundError, version as _pkg_version
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
from core.diagnostics import run_diagnostics
from core.exceptions import DeviceNotFoundError, NetFatherError
from core.logger import get_logger, setup_logging
from core.platform import get_platform_info
from core.version import VERSION
from manager.device_manager import DeviceManager
from manager.profile_manager import ProfileManager
from manager.rule_manager import RuleManager, schedule_is_active
from network.discovery import scan_network
from network.interface import get_network_status

log = get_logger("cli")

app = typer.Typer(
    name="netfather",
    help="NetFather - yerel ağ cihaz ve erişim yönetim aracı.",
    add_completion=True,
)

device_app = typer.Typer(help="Cihaz kayıtlarını yönetir.", no_args_is_help=True)
profile_app = typer.Typer(help="Cihaz profillerini yönetir.", no_args_is_help=True)
rules_app = typer.Typer(help="Zaman bazlı erişim kurallarını yönetir.", no_args_is_help=True)

app.add_typer(device_app, name="device")
app.add_typer(profile_app, name="profile")
app.add_typer(rules_app, name="rules")

_state: dict[str, Config | Database] = {}


def _get_version() -> str:
    """Return installed package version, or the source-tree development version."""
    try:
        return _pkg_version("netfather")
    except PackageNotFoundError:
        return f"{VERSION} (dev)"


def _version_callback(show_version: bool) -> None:
    if show_version:
        console.print(f"NetFather {_get_version()}")
        raise typer.Exit(code=0)


def _bootstrap() -> tuple[Config, Database]:
    """Initialize config, logging and database once for the current process."""
    if "config" in _state and "db" in _state:
        return _state["config"], _state["db"]  # type: ignore[return-value]

    config = load_config()
    setup_logging(config)
    db = get_database(config.database_path)
    _state["config"] = config
    _state["db"] = db
    return config, db


@app.callback(invoke_without_command=True)
def main_callback(
    ctx: typer.Context,
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="NetFather sürümünü gösterir ve çıkar.",
    ),
) -> None:
    """NetFather ana giriş noktası."""
    try:
        config, db = _bootstrap()
    except NetFatherError as exc:
        print_error(f"NetFather başlatılamadı: {exc}")
        raise typer.Exit(code=1) from exc

    # Interactive invocation opens the TUI. In pipes/CI, keep normal CLI
    # semantics and print help instead of attempting raw-terminal mode.
    if ctx.invoked_subcommand is None:
        if sys.stdin.isatty() and sys.stdout.isatty():
            from tui.app import run_tui

            run_tui(config, db)
        else:
            console.print(ctx.get_help())
        raise typer.Exit(code=0)


@app.command()
def tui(
    mode: str = typer.Option(
        "auto",
        "--mode",
        help="TUI modu: auto, fullscreen, inline veya plain.",
        show_default=True,
    ),
) -> None:
    """Interaktif Terminal UI'yi açar."""
    normalized_mode = mode.strip().lower()
    if normalized_mode not in {"auto", "fullscreen", "inline", "plain"}:
        print_error("Geçersiz TUI modu. Geçerli değerler: auto, fullscreen, inline, plain.")
        raise typer.Exit(code=2)

    config, db = _bootstrap()
    from tui.app import run_tui

    run_tui(config, db, mode=normalized_mode)


@app.command("platform")
def platform_info() -> None:
    """İşletim sistemi, mimari ve seçilen network backend'ini gösterir."""
    config, _ = _bootstrap()
    info = get_platform_info()
    print_title("Platform")
    table = make_table("Alan", "Değer")
    table.add_row("OS", info.system)
    table.add_row("Release", info.release or "-")
    table.add_row("Architecture", info.machine or "-")
    table.add_row("Official support", "yes" if info.supported else "experimental")
    table.add_row("Network backend", info.network_backend)
    table.add_row("Config", str(config.config_path))
    table.add_row("Data", str(config.data_dir))
    console.print(table)


@app.command()
def status() -> None:
    """Aktif ağ arayüzünü ve temel runtime yollarını gösterir."""
    config, _ = _bootstrap()
    net = get_network_status()
    info = get_platform_info()

    print_title("Network Status")
    table = make_table("Alan", "Değer")
    table.add_row("Platform", f"{info.system} ({info.machine or '-'})")
    table.add_row("Backend", info.network_backend)
    table.add_row("Interface", net.interface or "[dim]tespit edilemedi[/dim]")
    table.add_row("IP", net.local_ip or "[dim]tespit edilemedi[/dim]")
    table.add_row("Gateway", net.gateway or "[dim]tespit edilemedi[/dim]")
    table.add_row("Config", str(config.config_path))
    table.add_row("Database", str(config.database_path))
    console.print(table)


@app.command()
def doctor() -> None:
    """Kurulum ve runtime için zarar vermeyen tanılama kontrolleri çalıştırır."""
    config, db = _bootstrap()
    checks = run_diagnostics(config, db)

    print_title("Doctor")
    table = make_table("Durum", "Kontrol", "Detay")
    failures = 0
    for check in checks:
        if check.ok is True:
            status_text = "[green]OK[/green]"
        elif check.ok is False:
            status_text = "[red]FAIL[/red]"
            failures += 1
        else:
            status_text = "[yellow]WARN[/yellow]"
        table.add_row(status_text, check.name, check.detail)
    console.print(table)

    if failures:
        raise typer.Exit(code=1)


@app.command()
def scan(
    sync_known: bool = typer.Option(
        False,
        "--sync-known",
        help="Yalnızca zaten kayıtlı cihazların IP/vendor/last_seen bilgisini günceller.",
    )
) -> None:
    """İşletim sisteminin neighbor/ARP cache'i üzerinden pasif keşif yapar."""
    config, db = _bootstrap()
    hosts = scan_network(timeout_seconds=config.network.scan_timeout_seconds)

    if not hosts:
        print_info(
            "Hiçbir cihaz bulunamadı (aktif ağ olmayabilir veya işletim sisteminin komşu/ARP cache'i boş olabilir)."
        )
        return

    table = make_table("IP", "Arayüz", "MAC", "Durum", "Vendor", title="Keşfedilen Cihazlar")
    for host in hosts:
        table.add_row(
            host.ip,
            host.interface or "-",
            host.mac or "-",
            host.state or "-",
            host.vendor or "-",
        )
    console.print(table)

    if sync_known:
        updated = DeviceManager(db).sync_discovered_hosts(hosts)
        print_success(f"{updated} kayıtlı cihaz discovery sonucu ile güncellendi.")
    else:
        print_info("Sonuçlar otomatik kaydedilmedi. Kayıtlı cihazları güncellemek için --sync-known kullanın.")


@app.command()
def monitor() -> None:
    """Canlı trafik/erişim monitoring özelliğinin durumunu gösterir."""
    print_warning(
        "Canlı trafik monitoring ve firewall enforcement henüz uygulanmadı; "
        "TUI dashboard için 'netfather tui' kullanabilirsiniz."
    )


@app.command()
def config(
    show_path: bool = typer.Option(False, "--path", help="Sadece config dosyasının yolunu yazdırır."),
) -> None:
    """Aktif config değerlerini ve yolları gösterir."""
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
    table.add_row("Scan timeout", f"{cfg.network.scan_timeout_seconds}s")
    table.add_row("Monitor refresh", f"{cfg.monitor.refresh_seconds}s")
    console.print(table)


# ---------------------------------------------------------------------------
# Device commands
# ---------------------------------------------------------------------------


@device_app.command("list")
def device_list() -> None:
    """Kayıtlı tüm cihazları listeler."""
    _, db = _bootstrap()
    devices = DeviceManager(db).list_devices()
    if not devices:
        print_info("Henüz kayıtlı cihaz yok. 'netfather device add' ile ekleyebilirsiniz.")
        return

    table = make_table(
        "ID", "İsim", "MAC", "IP", "Vendor", "Tip", "Son Görülme", title="Kayıtlı Cihazlar"
    )
    for device in devices:
        table.add_row(
            str(device.id),
            device.name,
            device.mac,
            device.ip or "-",
            device.vendor or "-",
            device.device_type,
            device.last_seen.strftime("%Y-%m-%d %H:%M") if device.last_seen else "-",
        )
    console.print(table)


@device_app.command("info")
def device_info(name: str = typer.Argument(..., help="Cihaz ismi")) -> None:
    """Belirtilen cihazın detaylarını gösterir."""
    _, db = _bootstrap()
    try:
        device = DeviceManager(db).get_device_by_name(name)
    except DeviceNotFoundError as exc:
        print_error(str(exc))
        raise typer.Exit(code=1) from exc

    print_title(f"Device: {device.name}")
    table = make_table("Alan", "Değer")
    table.add_row("ID", str(device.id))
    table.add_row("İsim", device.name)
    table.add_row("MAC", device.mac)
    table.add_row("IP", device.ip or "-")
    table.add_row("Üretici", device.vendor or "-")
    table.add_row("Tip", device.device_type)
    table.add_row("Kayıt Tarihi", device.created_at.strftime("%Y-%m-%d %H:%M"))
    table.add_row(
        "Son Görülme",
        device.last_seen.strftime("%Y-%m-%d %H:%M") if device.last_seen else "-",
    )
    console.print(table)


@device_app.command("add")
def device_add(
    name: str = typer.Option(..., "--name", "-n", prompt=True, help="Cihaz ismi"),
    mac: str = typer.Option(..., "--mac", "-m", prompt=True, help="MAC adresi"),
    ip: Optional[str] = typer.Option(None, "--ip", help="IP adresi"),
    vendor: Optional[str] = typer.Option(None, "--vendor", help="Üretici adı"),
    device_type: str = typer.Option("unknown", "--type", "-t", help="Cihaz tipi"),
) -> None:
    """Yeni bir cihazı elle kaydeder."""
    _, db = _bootstrap()
    try:
        device = DeviceManager(db).add_device(
            name=name, mac=mac, ip=ip, vendor=vendor, device_type=device_type
        )
    except NetFatherError as exc:
        print_error(f"Cihaz eklenemedi: {exc}")
        raise typer.Exit(code=1) from exc
    print_success(f"Cihaz eklendi: {device.name} ({device.mac})")


@device_app.command("update")
def device_update(
    name: str = typer.Argument(..., help="Güncellenecek cihazın mevcut ismi"),
    new_name: Optional[str] = typer.Option(None, "--name", help="Yeni cihaz ismi"),
    mac: Optional[str] = typer.Option(None, "--mac", help="Yeni MAC adresi"),
    ip: Optional[str] = typer.Option(None, "--ip", help="Yeni IP adresi"),
    vendor: Optional[str] = typer.Option(None, "--vendor", help="Yeni vendor bilgisi"),
    device_type: Optional[str] = typer.Option(None, "--type", help="Yeni cihaz tipi"),
) -> None:
    """Kayıtlı bir cihazın alanlarını günceller."""
    if all(value is None for value in (new_name, mac, ip, vendor, device_type)):
        print_error("Güncellenecek en az bir alan vermelisiniz.")
        raise typer.Exit(code=2)

    _, db = _bootstrap()
    try:
        device = DeviceManager(db).update_device(
            name,
            new_name=new_name,
            mac=mac,
            ip=ip,
            vendor=vendor,
            device_type=device_type,
        )
    except NetFatherError as exc:
        print_error(f"Cihaz güncellenemedi: {exc}")
        raise typer.Exit(code=1) from exc
    print_success(f"Cihaz güncellendi: {device.name} ({device.mac})")


@device_app.command("remove")
def device_remove(
    name: str = typer.Argument(..., help="Silinecek cihaz ismi"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Onay istemeden siler."),
) -> None:
    """Kayıtlı bir cihazı siler; bağlı profil/kurallar cascade ile silinir."""
    _, db = _bootstrap()
    if not yes and not typer.confirm(f"'{name}' cihazı silinsin mi?"):
        print_info("İşlem iptal edildi.")
        raise typer.Exit(code=0)

    try:
        DeviceManager(db).delete_device(name)
    except DeviceNotFoundError as exc:
        print_error(str(exc))
        raise typer.Exit(code=1) from exc
    print_success(f"Cihaz silindi: {name}")


# ---------------------------------------------------------------------------
# Profile commands
# ---------------------------------------------------------------------------


@profile_app.command("list")
def profile_list(device: Optional[str] = typer.Option(None, "--device", "-d")) -> None:
    """Profilleri listeler; istenirse tek cihaza filtreler."""
    _, db = _bootstrap()
    try:
        profiles = ProfileManager(db).list_profiles(device)
    except NetFatherError as exc:
        print_error(str(exc))
        raise typer.Exit(code=1) from exc

    if not profiles:
        print_info("Profil bulunamadı.")
        return
    table = make_table("ID", "Cihaz", "Profil", "Internet Mode", title="Profiller")
    for profile in profiles:
        table.add_row(str(profile.id), profile.device.name, profile.name, profile.internet_mode)
    console.print(table)


@profile_app.command("create")
def profile_create(
    device: str = typer.Option(..., "--device", "-d", help="Kayıtlı cihaz ismi"),
    name: str = typer.Option(..., "--name", "-n", help="Profil ismi"),
    mode: str = typer.Option("unrestricted", "--mode", help="unrestricted|controlled|blocked"),
) -> None:
    """Bir cihaza profil oluşturur."""
    _, db = _bootstrap()
    try:
        profile = ProfileManager(db).create_profile(device, name, mode)
    except NetFatherError as exc:
        print_error(f"Profil oluşturulamadı: {exc}")
        raise typer.Exit(code=1) from exc
    print_success(f"Profil oluşturuldu: {profile.device.name} / {profile.name}")


@profile_app.command("set-mode")
def profile_set_mode(
    profile_id: int = typer.Argument(..., min=1),
    mode: str = typer.Argument(..., help="unrestricted|controlled|blocked"),
) -> None:
    """Profilin internet modunu değiştirir."""
    _, db = _bootstrap()
    try:
        profile = ProfileManager(db).set_mode(profile_id, mode)
    except NetFatherError as exc:
        print_error(str(exc))
        raise typer.Exit(code=1) from exc
    print_success(f"Profil modu güncellendi: id={profile.id} -> {profile.internet_mode}")


@profile_app.command("remove")
def profile_remove(
    profile_id: int = typer.Argument(..., min=1),
    yes: bool = typer.Option(False, "--yes", "-y"),
) -> None:
    """Profili siler."""
    if not yes and not typer.confirm(f"Profil id={profile_id} silinsin mi?"):
        raise typer.Exit(code=0)
    _, db = _bootstrap()
    try:
        ProfileManager(db).delete_profile(profile_id)
    except NetFatherError as exc:
        print_error(str(exc))
        raise typer.Exit(code=1) from exc
    print_success(f"Profil silindi: id={profile_id}")


# ---------------------------------------------------------------------------
# Rule commands
# ---------------------------------------------------------------------------


@rules_app.command("list")
def rules_list(device: Optional[str] = typer.Option(None, "--device", "-d")) -> None:
    """Tanımlı kuralları listeler."""
    _, db = _bootstrap()
    try:
        rules = RuleManager(db).list_rules(device)
    except NetFatherError as exc:
        print_error(str(exc))
        raise typer.Exit(code=1) from exc

    if not rules:
        print_info("Kural bulunamadı.")
        return
    table = make_table(
        "ID", "Cihaz", "Action", "Schedule", "Enabled", "Active now", "Açıklama", title="Kurallar"
    )
    for rule in rules:
        table.add_row(
            str(rule.id),
            rule.device.name,
            rule.action,
            rule.schedule,
            "yes" if rule.enabled else "no",
            "yes" if rule.enabled and schedule_is_active(rule.schedule) else "no",
            rule.description or "-",
        )
    console.print(table)


@rules_app.command("create")
def rules_create(
    device: str = typer.Option(..., "--device", "-d", help="Kayıtlı cihaz ismi"),
    action: str = typer.Option("block", "--action", "-a", help="allow|block"),
    schedule: str = typer.Option(..., "--schedule", "-s", help="HH:MM-HH:MM"),
    description: Optional[str] = typer.Option(None, "--description"),
    disabled: bool = typer.Option(False, "--disabled", help="Kuralı başlangıçta kapalı oluşturur."),
) -> None:
    """Zaman bazlı erişim kuralı oluşturur (enforcement yapmaz)."""
    _, db = _bootstrap()
    try:
        rule = RuleManager(db).create_rule(
            device,
            action,
            schedule,
            enabled=not disabled,
            description=description,
        )
    except NetFatherError as exc:
        print_error(f"Kural oluşturulamadı: {exc}")
        raise typer.Exit(code=1) from exc
    print_success(f"Kural oluşturuldu: id={rule.id} {rule.device.name} {rule.action} {rule.schedule}")


@rules_app.command("active")
def rules_active(device: Optional[str] = typer.Option(None, "--device", "-d")) -> None:
    """Şu anda aktif olan enabled kuralları listeler."""
    _, db = _bootstrap()
    try:
        rules = RuleManager(db).active_rules(device_name=device)
    except NetFatherError as exc:
        print_error(str(exc))
        raise typer.Exit(code=1) from exc
    if not rules:
        print_info("Şu anda aktif kural yok.")
        return
    table = make_table("ID", "Cihaz", "Action", "Schedule", "Açıklama")
    for rule in rules:
        table.add_row(str(rule.id), rule.device.name, rule.action, rule.schedule, rule.description or "-")
    console.print(table)


def _set_rule_enabled(rule_id: int, enabled: bool) -> None:
    _, db = _bootstrap()
    try:
        rule = RuleManager(db).set_enabled(rule_id, enabled)
    except NetFatherError as exc:
        print_error(str(exc))
        raise typer.Exit(code=1) from exc
    print_success(f"Kural {'aktif' if enabled else 'pasif'}: id={rule.id}")


@rules_app.command("enable")
def rules_enable(rule_id: int = typer.Argument(..., min=1)) -> None:
    """Kuralı etkinleştirir."""
    _set_rule_enabled(rule_id, True)


@rules_app.command("disable")
def rules_disable(rule_id: int = typer.Argument(..., min=1)) -> None:
    """Kuralı devre dışı bırakır."""
    _set_rule_enabled(rule_id, False)


@rules_app.command("remove")
def rules_remove(
    rule_id: int = typer.Argument(..., min=1),
    yes: bool = typer.Option(False, "--yes", "-y"),
) -> None:
    """Kuralı siler."""
    if not yes and not typer.confirm(f"Kural id={rule_id} silinsin mi?"):
        raise typer.Exit(code=0)
    _, db = _bootstrap()
    try:
        RuleManager(db).delete_rule(rule_id)
    except NetFatherError as exc:
        print_error(str(exc))
        raise typer.Exit(code=1) from exc
    print_success(f"Kural silindi: id={rule_id}")
