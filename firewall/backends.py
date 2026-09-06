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
        elements = ", ".join(ips)
        set_body = f"type ipv4_addr; elements = {{ {elements} }}" if ips else "type ipv4_addr;"
        return f'''table inet {self.table} {{
  set blocked4 {{ {set_body} }}
  chain input {{ type filter hook input priority 0; policy accept; ip saddr @blocked4 drop }}
  chain output {{ type filter hook output priority 0; policy accept; ip daddr @blocked4 drop }}
  chain forward {{ type filter hook forward priority 0; policy accept; ip saddr @blocked4 drop; ip daddr @blocked4 drop }}
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
        backup = existing.stdout if existing.returncode == 0 else ""
        if existing.returncode == 0:
            deleted = _run([nft, "delete", "table", "inet", self.table])
            if deleted.returncode != 0:
                raise RuntimeError(deleted.stderr.strip())
        result = _run([nft, "-f", "-"], input_text=script)
        if result.returncode != 0:
            if backup:
                _run([nft, "-f", "-"], input_text=backup)
            raise RuntimeError(f"nft apply failed: {result.stderr.strip()}")
        return FirewallResult(self.name, True, tuple(ips), "NetFather nftables table applied", script)

    def rollback(self, *, apply: bool = False) -> FirewallResult:
        if not apply:
            return FirewallResult(self.name, False, (), "dry-run rollback", f"delete table inet {self.table}")
        nft = shutil.which("nft")
        if not nft:
            raise RuntimeError("nft komutu bulunamadı.")
        result = _run([nft, "delete", "table", "inet", self.table])
        if result.returncode != 0 and "No such file" not in result.stderr:
            raise RuntimeError(result.stderr.strip())
        return FirewallResult(self.name, True, (), "NetFather nftables table removed")


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
