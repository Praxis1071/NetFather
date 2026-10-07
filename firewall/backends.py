"""Linux nftables firewall backend.

NetFather owns a dedicated nftables table and never flushes the host firewall.
"""
from __future__ import annotations

import shutil
import subprocess

from firewall.base import FirewallResult, normalize_local_ips


class FirewallBackend:
    name = "none"
    def preview(self, blocked_ips: list[str]) -> str:
        raise NotImplementedError
    def apply(self, blocked_ips: list[str], *, apply: bool = False) -> FirewallResult:
        raise NotImplementedError
    def rollback(self, *, apply: bool = False) -> FirewallResult:
        raise NotImplementedError


def _run(args: list[str], *, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, input=input_text, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)


class NftablesBackend(FirewallBackend):
    name = "nftables"
    table = "netfather"

    def preview(self, blocked_ips: list[str]) -> str:
        ips = normalize_local_ips(blocked_ips)
        ipv4 = [ip for ip in ips if ":" not in ip]
        ipv6 = [ip for ip in ips if ":" in ip]
        elements4 = ", ".join(ipv4)
        elements6 = ", ".join(ipv6)
        set_body4 = f"type ipv4_addr; elements = {{ {elements4} }}" if ipv4 else "type ipv4_addr;"
        set_body6 = f"type ipv6_addr; elements = {{ {elements6} }}" if ipv6 else "type ipv6_addr;"
        return f'''table inet {self.table} {{
  set blocked4 {{ {set_body4} }}
  set blocked6 {{ {set_body6} }}
  chain input {{
    type filter hook input priority 0;
    policy accept;
    ip saddr @blocked4 drop;
    ip6 saddr @blocked6 drop;
  }}
  chain output {{
    type filter hook output priority 0;
    policy accept;
    ip daddr @blocked4 drop;
    ip6 daddr @blocked6 drop;
  }}
  chain forward {{
    type filter hook forward priority 0;
    policy accept;
    ip saddr @blocked4 drop;
    ip daddr @blocked4 drop;
    ip6 saddr @blocked6 drop;
    ip6 daddr @blocked6 drop;
  }}
}}'''

    def apply(self, blocked_ips: list[str], *, apply: bool = False) -> FirewallResult:
        ips = normalize_local_ips(blocked_ips)
        script = self.preview(ips)
        if not apply:
            return FirewallResult(self.name, False, tuple(ips), "dry-run", script)
        nft = shutil.which("nft")
        if not nft:
            raise RuntimeError("nft komutu bulunamadı.")
        check_script = script.replace(f"table inet {self.table}", "table inet netfather_check", 1)
        checked = _run([nft, "-c", "-f", "-"], input_text=check_script)
        if checked.returncode != 0:
            raise RuntimeError(f"nft validation failed: {checked.stderr.strip()}")
        existing = _run([nft, "list", "table", "inet", self.table])
        if existing.returncode != 0:
            # First installation: create the complete NetFather-owned table.
            result = _run([nft, "-f", "-"], input_text=script)
            if result.returncode != 0:
                raise RuntimeError(f"nft apply failed: {result.stderr.strip()}")
            return FirewallResult(self.name, True, tuple(ips), "NetFather nftables table created", script)

        # Upgrade a table created by older NetFather versions without deleting
        # it.  This preserves existing counters and blocking state while adding
        # the IPv6 set/rules required by the dual-stack backend.
        if "set blocked6" not in existing.stdout:
            upgrade_script = (
                f"add set inet {self.table} blocked6 {{ type ipv6_addr; }}\n"
                f"add rule inet {self.table} input ip6 saddr @blocked6 drop\n"
                f"add rule inet {self.table} output ip6 daddr @blocked6 drop\n"
                f"add rule inet {self.table} forward ip6 saddr @blocked6 drop\n"
                f"add rule inet {self.table} forward ip6 daddr @blocked6 drop\n"
            )
            checked_upgrade = _run([nft, "-c", "-f", "-"], input_text=upgrade_script)
            if checked_upgrade.returncode != 0:
                raise RuntimeError(f"nft IPv6 upgrade validation failed: {checked_upgrade.stderr.strip()}")
            upgraded = _run([nft, "-f", "-"], input_text=upgrade_script)
            if upgraded.returncode != 0:
                raise RuntimeError(f"nft IPv6 upgrade failed: {upgraded.stderr.strip()}")

        # Existing NetFather state is updated in one nft transaction.  Do not
        # delete/recreate the table: that would unnecessarily reset counters,
        # briefly remove enforcement, and make rollback more fragile.
        ipv4 = [ip for ip in ips if ":" not in ip]
        ipv6 = [ip for ip in ips if ":" in ip]
        update_lines = [
            f"flush set inet {self.table} blocked4",
            f"flush set inet {self.table} blocked6",
        ]
        if ipv4:
            update_lines.append(
                f"add element inet {self.table} blocked4 {{ {', '.join(ipv4)} }}"
            )
        if ipv6:
            update_lines.append(
                f"add element inet {self.table} blocked6 {{ {', '.join(ipv6)} }}"
            )
        update_script = "\n".join(update_lines) + "\n"
        checked_update = _run([nft, "-c", "-f", "-"], input_text=update_script)
        if checked_update.returncode != 0:
            raise RuntimeError(f"nft validation failed: {checked_update.stderr.strip()}")
        result = _run([nft, "-f", "-"], input_text=update_script)
        if result.returncode != 0:
            raise RuntimeError(f"nft atomic update failed: {result.stderr.strip()}")
        return FirewallResult(self.name, True, tuple(ips), "NetFather nftables set updated atomically", update_script)

    def rollback(self, *, apply: bool = False) -> FirewallResult:
        """Disable NetFather blocking without destroying its owned nftables state."""
        script = (
            f"flush set inet {self.table} blocked4\n"
            f"flush set inet {self.table} blocked6\n"
        )
        if not apply:
            return FirewallResult(self.name, False, (), "dry-run rollback", script)
        nft = shutil.which("nft")
        if not nft:
            raise RuntimeError("nft komutu bulunamadı.")
        checked = _run([nft, "-c", "-f", "-"], input_text=script)
        if checked.returncode != 0:
            raise RuntimeError(f"nft rollback validation failed: {checked.stderr.strip()}")
        result = _run([nft, "-f", "-"], input_text=script)
        if result.returncode != 0:
            raise RuntimeError(f"nft rollback failed: {result.stderr.strip()}")
        return FirewallResult(self.name, True, (), "NetFather blocking set cleared", script)


class NullFirewallBackend(FirewallBackend):
    name = "none"
    def preview(self, blocked_ips: list[str]) -> str:
        return "Firewall enforcement disabled"
    def apply(self, blocked_ips: list[str], *, apply: bool = False) -> FirewallResult:
        return FirewallResult(self.name, False, tuple(normalize_local_ips(blocked_ips)), "disabled")
    def rollback(self, *, apply: bool = False) -> FirewallResult:
        return FirewallResult(self.name, False, (), "disabled")


def get_firewall_backend(name: str = "auto") -> FirewallBackend:
    normalized = name.strip().lower()
    if normalized == "none":
        return NullFirewallBackend()
    if normalized not in {"auto", "nftables"}:
        raise ValueError("Linux için firewall backend yalnızca auto, nftables veya none olabilir.")
    return NftablesBackend()
