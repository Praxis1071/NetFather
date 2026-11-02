"""Optional read-only LAN name/lease enrichment; never reachability evidence."""
from __future__ import annotations

import ipaddress
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from core.operations import CancellationToken, run_process
from core.time_utils import utc_now

DEFAULT_LEASE_PATHS = ("/var/lib/misc/dnsmasq.leases", "/var/lib/dnsmasq/dnsmasq.leases",
                       "/var/lib/dhcp/dhcpd.leases")


def parse_leases(raw: str, *, now: int | None = None) -> dict[tuple[str, str], str]:
    """Parse unexpired dnsmasq leases and active ISC dhcpd lease blocks."""
    now = int(utc_now().replace(tzinfo=timezone.utc).timestamp()) if now is None else now
    leases = {}
    for line in raw.splitlines():
        fields = line.split()
        if len(fields) >= 4 and fields[0].isdigit():
            expiry, mac, address, name = fields[:4]
            if int(expiry) and int(expiry) <= now or name == "*":
                continue
            try:
                ipaddress.ip_address(address)
            except ValueError:
                continue
            if re.fullmatch(r"(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}", mac):
                leases[(address, mac.lower())] = name[:255]
    # Last block wins, including expired/free records that invalidate old ones.
    for address, block in re.findall(r"lease\s+(\S+)\s*\{([^}]+)\}", raw):
        mac = re.search(r"hardware\s+ethernet\s+([\da-fA-F:]+)\s*;", block)
        name = re.search(r'client-hostname\s+"([^"\n]+)"\s*;', block)
        if not mac:
            continue
        key = (address, mac[1].lower())
        leases.pop(key, None)
        if "binding state active;" not in block or not name:
            continue
        end = re.search(r"ends\s+\d+\s+([\d/]+)\s+([\d:]+)\s*;", block)
        if end:
            try:
                expiry = datetime.strptime(f"{end[1]} {end[2]}", "%Y/%m/%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp()
            except ValueError:
                continue
            if expiry <= now:
                continue
        else:
            continue  # A lease of unknown age must not overwrite a name.
        leases[key] = name[1][:255]
    return leases


def enrich_leases(hosts, paths: tuple[str, ...] | None = None) -> tuple[str, ...]:
    leases, warnings = {}, []
    for name in DEFAULT_LEASE_PATHS if paths is None else paths:
        path = Path(name)
        try:
            with path.open(encoding="utf-8", errors="replace") as stream:
                raw = stream.read(4 * 1024 * 1024 + 1)
            if len(raw) > 4 * 1024 * 1024:
                warnings.append(f"DHCP lease file exceeds the 4 MiB limit: {path}")
                continue
            leases.update(parse_leases(raw))
        except FileNotFoundError:
            continue
        except OSError as exc:
            warnings.append(f"DHCP lease enrichment unavailable ({path}): {exc}")
    for host in hosts:
        name = leases.get((host.ip, (host.mac or "").lower()))
        if name and not host.hostname:
            host.hostname = name
            host.source += "+dhcp"
    return tuple(warnings)


def resolve_local_name(address: str, interface: str | None, *, token: CancellationToken | None = None) -> str | None:
    """Use system mDNS/LLMNR when available, with optional NetBIOS fallback.

    Only already observed private/link-local hosts are queried. No broadcast
    subnet sweep or external discovery is performed.
    """
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return None
    if not (ip.is_private or ip.is_link_local) or ip.is_multicast or ip.is_loopback:
        return None
    commands = []
    resolved = shutil.which("resolvectl")
    if resolved:
        command = [resolved, "--legend=no", "--protocol=mdns", "--protocol=llmnr"]
        if interface:
            command += ["--interface", interface]
        commands.append(command + ["query", address])
    netbios = shutil.which("nmblookup") if ip.version == 4 else None
    if netbios:
        commands.append([netbios, "-A", address])
    for command in commands:
        try:
            result = run_process(command, token=token, capture_output=True, text=True,
                                 timeout=2, check=False)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if result.returncode:
            continue
        if command[0] == resolved:
            line = result.stdout.splitlines()[0] if result.stdout.splitlines() else ""
            _, separator, value = line.partition(": ")
            if separator and value.strip():
                return value.split()[0].rstrip(".")[:255]
        else:
            for line in result.stdout.splitlines():
                match = re.match(r"\s*(\S+)\s+<00>\s+-\s+", line)
                if match and "GROUP" not in line:
                    return match[1][:255]
    return None
