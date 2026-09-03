"""
TUI için Rich tabanlı render fonksiyonları.

Her fonksiyon saf girdi → Rich renderable çıktısı üretir; hiçbir I/O,
subprocess veya veritabanı erişimi yapmaz (bunlar `tui/data.py`'de
tamamlanmış olarak buraya gelir). Bu ayrım sayesinde iş mantığı
(`tui/data.py`, `tui/state.py`) Rich olmadan test edilebilir kalır.

Semantic renkler tutarlı şekilde kullanılır:
    OK      -> yeşil
    WARNING -> sarı
    ERROR   -> kırmızı
    UNKNOWN -> soluk/gri
"""

from __future__ import annotations

import datetime as dt

from rich.console import Console, Group, RenderableType
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from network.discovery import DiscoveredHost
from network.interface import NetworkStatus
from manager.rule_manager import schedule_is_active
from tui.data import DiscoveryData, OverviewData
from tui.state import NAV_ORDER, AppState, Screen

COLOR_OK = "bold green"
COLOR_WARNING = "bold yellow"
COLOR_ERROR = "bold red"
COLOR_UNKNOWN = "dim"

UNKNOWN_TEXT = "Unknown"
NOT_CHECKED_TEXT = "Not checked"
NA_TEXT = "N/A"


def _humanize_timedelta(since: dt.datetime | None) -> str:
    """Bir zaman damgasını 'X sec ago' / 'X min ago' gibi kısa, okunabilir bir metne çevirir."""
    if since is None:
        return "Never"
    delta = dt.datetime.now() - since
    seconds = int(delta.total_seconds())
    if seconds < 0:
        seconds = 0
    if seconds < 60:
        return f"{seconds} sec ago"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} min ago"
    hours = minutes // 60
    return f"{hours} hr ago"


# ---------------------------------------------------------------------------
# Header / Footer
# ---------------------------------------------------------------------------


def render_header(system_ok: bool | None) -> RenderableType:
    """Üst başlık çubuğunu oluşturur: 'NETFATHER' + genel sistem durumu göstergesi."""
    if system_ok is True:
        status = Text("● SYSTEM OK", style=COLOR_OK)
    elif system_ok is False:
        status = Text("● SYSTEM ISSUE", style=COLOR_ERROR)
    else:
        status = Text("● STATUS UNKNOWN", style=COLOR_UNKNOWN)

    grid = Table.grid(expand=True)
    grid.add_column(justify="left", ratio=1)
    grid.add_column(justify="right")
    grid.add_row(Text("NETFATHER", style="bold cyan"), status)
    return Panel(grid, style="cyan", padding=(0, 1))


def render_footer(status_message: str | None = None, compact: bool = False) -> RenderableType:
    """Alt klavye kısayolu çubuğunu oluşturur (varsa geçici bir durum mesajıyla)."""
    if status_message:
        return Panel(Text(status_message, justify="center", style="bold yellow"), padding=(0, 1))
    if compact:
        hints = "↑↓/j k Navigate  Enter Select  r Refresh  s Sync  q Quit"
    else:
        hints = "↑↓/j k Navigate   Enter Select   r Refresh/Scan   s Sync known   q Quit"
    return Panel(Text(hints, justify="center", style="dim"), padding=(0, 1))


# ---------------------------------------------------------------------------
# Overview (üst özet şeridi + Overview ekranının tam içeriği)
# ---------------------------------------------------------------------------


def render_overview_strip(data: OverviewData, compact: bool = False) -> RenderableType:
    """
    Her zaman görünen, kompakt Overview özet şeridini oluşturur.

    Yalnızca gerçek verilerden beslenir; tespit edilemeyen alanlar
    "Unknown"/"N/A" olarak gösterilir, asla uydurulmaz.
    """
    interface = data.interface or (UNKNOWN_TEXT if not data.network_status_known else NA_TEXT)
    local_ip = data.local_ip or (UNKNOWN_TEXT if not data.network_status_known else NA_TEXT)
    gateway = data.gateway or (UNKNOWN_TEXT if not data.network_status_known else NA_TEXT)

    # Mevcut mimaride genel internet erişilebilirlik kontrolü yok; bunu
    # asla "Connected" gibi sahte göstermiyoruz.
    internet_text = Text(NOT_CHECKED_TEXT, style=COLOR_UNKNOWN)

    device_count = (
        str(data.registered_device_count) if data.registered_device_count is not None else UNKNOWN_TEXT
    )
    last_scan = _humanize_timedelta(data.last_scan_time)

    if compact:
        grid = Table.grid(padding=(0, 1), expand=True)
        grid.add_column(style="dim")
        grid.add_column(ratio=1)
        grid.add_row("Network", interface)
        grid.add_row("Local IP", local_ip)
        grid.add_row("Gateway", gateway)
        grid.add_row("Devices", device_count)
        grid.add_row("Last Scan", last_scan)
        return Panel(grid, title="OVERVIEW", title_align="left", padding=(0, 1))

    grid = Table.grid(padding=(0, 2), expand=True)
    grid.add_column(style="dim", ratio=1)
    grid.add_column(ratio=2)
    grid.add_column(style="dim", ratio=1)
    grid.add_column(ratio=2)

    grid.add_row("Network", interface, "Gateway", gateway)
    grid.add_row("Local IP", local_ip, "Internet", internet_text)
    grid.add_row("Devices", device_count, "Last Scan", last_scan)

    return Panel(grid, title="OVERVIEW", title_align="left", padding=(1, 2))


def render_overview_screen(data: OverviewData) -> RenderableType:
    """Overview ekranı seçiliyken Active View panelinde gösterilen genişletilmiş içerik."""
    parts: list[RenderableType] = [render_overview_strip(data)]

    extra = Table.grid(padding=(0, 2), expand=True)
    extra.add_column(style="dim", ratio=1)
    extra.add_column(ratio=2)

    if data.database_ok:
        db_text = Text("OK", style=COLOR_OK)
    else:
        db_text = Text(f"ERROR: {data.database_error}", style=COLOR_ERROR)
    extra.add_row("Database", db_text)

    if data.last_scan_error:
        extra.add_row("Last Scan Result", Text(data.last_scan_error, style=COLOR_WARNING))
    elif data.last_scan_device_count is not None:
        extra.add_row(
            "Last Scan Result", Text(f"{data.last_scan_device_count} host(s) found", style=COLOR_OK)
        )
    else:
        extra.add_row("Last Scan Result", Text("Not scanned yet this session", style=COLOR_UNKNOWN))

    parts.append(Panel(extra, title="System", title_align="left"))
    return Group(*parts)


# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------


def render_navigation(state: AppState, compact: bool = False) -> RenderableType:
    """Navigasyon panelini, seçili öğeyi vurgulayarak oluşturur."""
    if compact:
        selected = NAV_ORDER[state.nav_index]
        text = Text()
        text.append(f"{state.nav_index + 1}/{len(NAV_ORDER)}  ", style="dim")
        text.append(selected.value, style="bold cyan")
        text.append("  •  Enter opens", style="dim")
        return Panel(text, title="NAVIGATION", title_align="left", padding=(0, 1))

    lines: list[Text] = []
    for index, screen in enumerate(NAV_ORDER):
        is_selected = index == state.nav_index
        marker = "> " if is_selected else "  "
        style = "bold cyan" if is_selected else ""
        lines.append(Text(f"{marker}{screen.value}", style=style))

    return Panel(Group(*lines), title="NAVIGATION", title_align="left", padding=(1, 1))


# ---------------------------------------------------------------------------
# Network ekranı
# ---------------------------------------------------------------------------


def render_network_screen(status: NetworkStatus) -> RenderableType:
    """Network ekranının içeriği — doğrudan `get_network_status()` sonucundan."""
    is_known = status != NetworkStatus()

    table = Table.grid(padding=(0, 2))
    table.add_column(style="dim")
    table.add_column()
    table.add_row("Interface", status.interface or (UNKNOWN_TEXT if not is_known else NA_TEXT))
    table.add_row("Local IP", status.local_ip or (UNKNOWN_TEXT if not is_known else NA_TEXT))
    table.add_row("Gateway", status.gateway or (UNKNOWN_TEXT if not is_known else NA_TEXT))
    table.add_row("Netmask", status.netmask or NA_TEXT)

    if not is_known:
        note = Text(
            "Ağ arayüzü tespit edilemedi ('ip' komutu bulunamadı ya da varsayılan rota yok).",
            style=COLOR_WARNING,
        )
        return Group(table, note)
    return table


# ---------------------------------------------------------------------------
# Discovery ekranı
# ---------------------------------------------------------------------------


def _hosts_table(hosts: list[DiscoveredHost]) -> Table:
    table = Table(expand=True)
    table.add_column("IP", overflow="fold")
    table.add_column("Interface")
    table.add_column("MAC", overflow="fold")
    table.add_column("State")
    table.add_column("Vendor")
    for host in hosts:
        table.add_row(host.ip, host.interface or "-", host.mac or "-", host.state or "-", host.vendor or "-")
    return table


def render_discovery_screen(data: DiscoveryData) -> RenderableType:
    """Discovery ekranının içeriği: backend bilgisi, son tarama, sonuç tablosu."""
    header = Table.grid(padding=(0, 2))
    header.add_column(style="dim")
    header.add_column()
    header.add_row("Backend", data.backend)
    header.add_row("Last Scan", _humanize_timedelta(data.last_scan_time))

    parts: list[RenderableType] = [header]

    if data.last_scan_error:
        parts.append(Text(data.last_scan_error, style=COLOR_WARNING))
    elif data.hosts:
        parts.append(_hosts_table(data.hosts))
    else:
        parts.append(Text("Not scanned yet this session.", style=COLOR_UNKNOWN))

    parts.append(Text("\n[ r ] Scan Now", style="bold"))
    return Group(*parts)


# ---------------------------------------------------------------------------
# Devices ekranı
# ---------------------------------------------------------------------------


def render_devices_screen(
    registered_devices: list, registered_error: str | None, discovery: DiscoveryData
) -> RenderableType:
    """
    Devices ekranı: kayıtlı cihazlar (DB) ve son keşfedilenler (discovery)
    AYRI, açıkça etiketlenmiş iki bölüm olarak gösterilir; karıştırılmaz.
    """
    registered_table = Table(title="Registered Devices (database)", expand=True)
    registered_table.add_column("Name")
    registered_table.add_column("MAC", overflow="fold")
    registered_table.add_column("IP")
    registered_table.add_column("Vendor")
    registered_table.add_column("Type")
    registered_table.add_column("Last Seen")

    if registered_error:
        registered_table.add_row(Text(f"Error: {registered_error}", style=COLOR_ERROR), "", "", "", "", "")
    elif not registered_devices:
        registered_table.add_row(Text("No registered devices.", style=COLOR_UNKNOWN), "", "", "", "", "")
    else:
        for device in registered_devices:
            last_seen = device.last_seen.strftime("%Y-%m-%d %H:%M") if device.last_seen else "-"
            registered_table.add_row(device.name, device.mac, device.ip or "-", device.vendor or "-", device.device_type, last_seen)

    discovered_table: RenderableType
    if discovery.last_scan_error:
        discovered_table = Text(discovery.last_scan_error, style=COLOR_WARNING)
    elif discovery.hosts:
        discovered_table = _hosts_table(discovery.hosts)
    else:
        discovered_table = Text("Not scanned yet this session.", style=COLOR_UNKNOWN)

    return Group(
        registered_table,
        Panel(discovered_table, title="Recently Discovered (not saved)", title_align="left"),
    )


# ---------------------------------------------------------------------------
# Configuration / Logs / Placeholder ekranları
# ---------------------------------------------------------------------------


def render_profiles_screen(profiles: list, error: str | None) -> RenderableType:
    """Render persisted device profiles."""
    table = Table(expand=True)
    table.add_column("ID", justify="right")
    table.add_column("Device")
    table.add_column("Profile")
    table.add_column("Internet mode")
    if error:
        table.add_row("-", Text(error, style=COLOR_ERROR), "", "")
    elif not profiles:
        table.add_row("-", Text("No profiles configured.", style=COLOR_UNKNOWN), "", "")
    else:
        for profile in profiles:
            table.add_row(
                str(profile.id),
                profile.device.name if getattr(profile, "device", None) else str(profile.device_id),
                profile.name,
                profile.internet_mode,
            )
    return Group(table, Text("\nManage with: netfather profile --help", style=COLOR_UNKNOWN))


def render_rules_screen(rules: list, error: str | None) -> RenderableType:
    """Render persisted rules and whether they are active right now."""
    table = Table(expand=True)
    table.add_column("ID", justify="right")
    table.add_column("Device")
    table.add_column("Action")
    table.add_column("Schedule")
    table.add_column("Enabled")
    table.add_column("Active now")
    table.add_column("Description")
    if error:
        table.add_row("-", Text(error, style=COLOR_ERROR), "", "", "", "", "")
    elif not rules:
        table.add_row("-", Text("No rules configured.", style=COLOR_UNKNOWN), "", "", "", "", "")
    else:
        for rule in rules:
            if not rule.enabled:
                active_text = Text("no", style=COLOR_UNKNOWN)
            else:
                try:
                    active_text = (
                        Text("yes", style=COLOR_OK)
                        if schedule_is_active(rule.schedule)
                        else Text("no", style=COLOR_UNKNOWN)
                    )
                except Exception:  # legacy/corrupt DB value: render, do not crash TUI
                    active_text = Text("invalid", style=COLOR_ERROR)
            table.add_row(
                str(rule.id),
                rule.device.name if getattr(rule, "device", None) else str(rule.device_id),
                rule.action,
                rule.schedule,
                "yes" if rule.enabled else "no",
                active_text,
                rule.description or "-",
            )
    return Group(table, Text("\nManage with: netfather rules --help", style=COLOR_UNKNOWN))


def render_configuration_screen(rows: list[tuple[str, str]]) -> RenderableType:
    table = Table.grid(padding=(0, 2))
    table.add_column(style="dim")
    table.add_column()
    for label, value in rows:
        table.add_row(label, value)
    return table


def render_logs_screen(lines: list[str], message: str | None) -> RenderableType:
    if message:
        return Text(message, style=COLOR_UNKNOWN)
    return Text("\n".join(lines))


def render_placeholder_screen(message: str) -> RenderableType:
    """Rules/Monitor gibi henüz uygulanmamış ekranlar için nötr bilgilendirme."""
    return Text(message, style=COLOR_UNKNOWN)


def render_terminal_too_small(width: int, height: int) -> RenderableType:
    """Render a useful message instead of a broken layout on tiny terminals."""
    message = Text()
    message.append("Terminal window is too small for the interactive layout.\n", style="bold yellow")
    message.append(f"Current size: {width}x{height}. Resize to at least 44x14.\n\n", style="dim")
    message.append("q", style="bold cyan")
    message.append(" quit   ")
    message.append("r", style="bold cyan")
    message.append(" refresh")
    return Panel(message, title="NETFATHER", border_style="cyan", padding=(1, 2))


# ---------------------------------------------------------------------------
# Tam sayfa düzeni
# ---------------------------------------------------------------------------


def render_active_view(state: AppState, screen_content: RenderableType) -> RenderableType:
    """Sağdaki Active View panelini, seçili ekranın adı ve içeriğiyle sarmalar."""
    return Panel(screen_content, title=f"ACTIVE VIEW — {state.current_screen.value}", title_align="left")


# Terminal genişliği hiç tespit edilemezse (ör. son derece uç bir ortam)
# kullanılacak makul bir varsayılan. Normal koşullarda hiç kullanılmaz.
_FALLBACK_MEASURE_WIDTH = 80


def _measure_renderable_height(renderable: RenderableType, console: Console, width: int) -> int:
    """
    Bir renderable'ın (ör. bir Panel) verilen genişlikte GERÇEKTEN kaç
    satır tutacağını Rich'in kendi render motorunu kullanarak ölçer.

    Bu fonksiyon, header/overview/footer gibi sabit yükseklikli Layout
    bölgeleri için `size=` değerini ELLE TAHMİN ETMEK yerine DOĞRUDAN
    HESAPLAMAK içindir. Böylece bu panellerin içeriği (padding, border,
    satır sayısı) ileride değişse bile Layout boyutu otomatik olarak
    doğru kalır — sabit bir "sihirli sayı" bir daha asla içerikle senkron
    dışı kalamaz. (Bu projede tam olarak bu tür bir senkron-dışılık,
    Overview panelinin `size=6` ile sabitlenmesine rağmen gerçekte 7
    satıra ihtiyaç duymasına yol açmıştı.)

    Args:
        renderable: Yüksekliği ölçülecek renderable (ör. bir Panel).
        console: Ölçüm için kullanılacak Console (gerçek terminal genişliği
            veya render seçenekleri buradan alınır).
        width: Renderable'ın render edileceği genişlik (kolon sayısı).

    Returns:
        Renderable'ın bu genişlikte kapladığı satır sayısı.
    """
    safe_width = width if width and width > 0 else _FALLBACK_MEASURE_WIDTH
    options = console.options.update(width=safe_width, height=None)
    lines = console.render_lines(renderable, options, pad=False)
    return len(lines)


def build_layout(
    console: Console,
    header: RenderableType,
    overview_strip: RenderableType,
    navigation: RenderableType,
    active_view: RenderableType,
    footer: RenderableType,
    compact: bool = False,
) -> Layout:
    """
    Tüm sayfayı doküman'daki yerleşime uygun şekilde birleştirir:
    Header / Overview şeridi / (Navigation | Active View) / Footer.

    Header/Overview/Footer bölgelerinin Layout `size=` değerleri sabit
    sayılar olarak YAZILMAZ; her birinin GERÇEK doğal yüksekliği
    `_measure_renderable_height()` ile ölçülüp kullanılır. Bu üç bölgenin
    yüksekliği yalnızca kendi içeriğine bağlıdır (terminal yüksekliğine
    değil), bu yüzden ölçülmüş bir sabit değer burada doğru araçtır;
    "body" (Navigation/Active View) ise kalan tüm dikey alanı `ratio` ile
    paylaşır ve terminale göre otomatik büyür/küçülür.
    """
    width = console.size.width

    header_height = _measure_renderable_height(header, console, width)
    overview_height = _measure_renderable_height(overview_strip, console, width)
    footer_height = _measure_renderable_height(footer, console, width)

    layout = Layout()
    layout.split_column(
        Layout(header, name="header", size=header_height, minimum_size=header_height),
        Layout(overview_strip, name="overview", size=overview_height, minimum_size=overview_height),
        Layout(name="body"),
        Layout(footer, name="footer", size=footer_height, minimum_size=footer_height),
    )
    if compact:
        navigation_height = _measure_renderable_height(navigation, console, width)
        layout["body"].split_column(
            Layout(
                navigation,
                name="navigation",
                size=navigation_height,
                minimum_size=navigation_height,
            ),
            Layout(active_view, name="active_view", ratio=1),
        )
    else:
        layout["body"].split_row(
            Layout(navigation, name="navigation", ratio=1, minimum_size=18),
            Layout(active_view, name="active_view", ratio=3),
        )
    return layout
