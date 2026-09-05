"""nftables, Windows Firewall and macOS PF backends.

Each backend owns a narrowly-scoped NetFather namespace and never flushes the
host firewall globally. ``apply=False`` is a real dry-run that returns the
exact rules/script without making privileged changes.
"""
from __future__ import annotations
import os
import shutil
import subprocess
from core.platform import PlatformFamily, platform_family
from firewall.base import FirewallResult, normalize_local_ips

class FirewallBackend:
    name = "none"
    def preview(self, blocked_ips: list[str]) -> str: raise NotImplementedError
    def apply(self, blocked_ips: list[str], *, apply: bool = False) -> FirewallResult: raise NotImplementedError
    def rollback(self, *, apply: bool = False) -> FirewallResult: raise NotImplementedError


def _run(args: list[str], *, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, input=input_text, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", check=False)

class NftablesBackend(FirewallBackend):
    name = "nftables"
    table = "netfather"
    def preview(self, blocked_ips: list[str]) -> str:
        ips = normalize_local_ips(blocked_ips)
        elements = ", ".join(ips)
        set_body = f"type ipv4_addr; elements = {{ {elements} }}" if ips else "type ipv4_addr;"
        return f'''table inet {self.table} {{
  set blocked4 {{ {set_body} }}
  chain input {{
    type filter hook input priority 0; policy accept;
    ip saddr @blocked4 drop
  }}
  chain output {{
    type filter hook output priority 0; policy accept;
    ip daddr @blocked4 drop
  }}
  chain forward {{
    type filter hook forward priority 0; policy accept;
    ip saddr @blocked4 drop
    ip daddr @blocked4 drop
  }}
}}'''
    def apply(self, blocked_ips: list[str], *, apply: bool = False) -> FirewallResult:
        ips = normalize_local_ips(blocked_ips); script = self.preview(ips)
        if not apply: return FirewallResult(self.name, False, tuple(ips), "dry-run", script)
        nft = shutil.which("nft")
        if not nft: raise RuntimeError("nft komutu bulunamadı.")
        # Validate with a temporary table name before touching active rules.
        check_script = script.replace(f"table inet {self.table}", "table inet netfather_check", 1)
        checked = _run([nft, "-c", "-f", "-"], input_text=check_script)
        if checked.returncode != 0: raise RuntimeError(f"nft validation failed: {checked.stderr.strip()}")
        existing = _run([nft, "list", "table", "inet", self.table])
        backup = existing.stdout if existing.returncode == 0 else ""
        if existing.returncode == 0:
            deleted = _run([nft, "delete", "table", "inet", self.table])
            if deleted.returncode != 0: raise RuntimeError(deleted.stderr.strip())
        result = _run([nft, "-f", "-"], input_text=script)
        if result.returncode != 0:
            if backup: _run([nft, "-f", "-"], input_text=backup)
            raise RuntimeError(f"nft apply failed: {result.stderr.strip()}")
        return FirewallResult(self.name, True, tuple(ips), "NetFather nftables table applied", script)
    def rollback(self, *, apply: bool = False) -> FirewallResult:
        if not apply: return FirewallResult(self.name, False, (), "dry-run rollback", f"delete table inet {self.table}")
        nft = shutil.which("nft");
        if not nft: raise RuntimeError("nft komutu bulunamadı.")
        result = _run([nft, "delete", "table", "inet", self.table])
        if result.returncode != 0 and "No such file" not in result.stderr:
            raise RuntimeError(result.stderr.strip())
        return FirewallResult(self.name, True, (), "NetFather nftables table removed")

class WindowsFirewallBackend(FirewallBackend):
    name = "windows"
    group = "NetFather"
    def _powershell(self) -> str:
        shell = shutil.which("powershell.exe") or shutil.which("pwsh")
        if not shell: raise RuntimeError("PowerShell bulunamadı.")
        return shell
    def preview(self, blocked_ips: list[str]) -> str:
        ips = normalize_local_ips(blocked_ips)
        lines = [f"Get-NetFirewallRule -Group '{self.group}' -ErrorAction SilentlyContinue | Remove-NetFirewallRule"]
        for i, ip in enumerate(ips, 1):
            lines += [
                f"New-NetFirewallRule -DisplayName 'NetFather Block {i} In' -Group '{self.group}' -Direction Inbound -Action Block -RemoteAddress '{ip}'",
                f"New-NetFirewallRule -DisplayName 'NetFather Block {i} Out' -Group '{self.group}' -Direction Outbound -Action Block -RemoteAddress '{ip}'",
            ]
        return ";\n".join(lines)
    def apply(self, blocked_ips: list[str], *, apply: bool = False) -> FirewallResult:
        ips = normalize_local_ips(blocked_ips); script = self.preview(ips)
        if not apply: return FirewallResult(self.name, False, tuple(ips), "dry-run", script)
        result = _run([self._powershell(), "-NoProfile", "-NonInteractive", "-Command", script])
        if result.returncode != 0: raise RuntimeError(f"Windows Firewall apply failed: {result.stderr.strip()}")
        return FirewallResult(self.name, True, tuple(ips), "NetFather Windows Firewall rules applied", script)
    def rollback(self, *, apply: bool = False) -> FirewallResult:
        script = f"Get-NetFirewallRule -Group '{self.group}' -ErrorAction SilentlyContinue | Remove-NetFirewallRule"
        if not apply: return FirewallResult(self.name, False, (), "dry-run rollback", script)
        result = _run([self._powershell(), "-NoProfile", "-NonInteractive", "-Command", script])
        if result.returncode != 0: raise RuntimeError(result.stderr.strip())
        return FirewallResult(self.name, True, (), "NetFather Windows Firewall rules removed")

class PfBackend(FirewallBackend):
    name = "pf"
    anchor = "com.apple/netfather"
    def preview(self, blocked_ips: list[str]) -> str:
        ips = normalize_local_ips(blocked_ips)
        return "\n".join([f"block drop quick from {ip} to any\nblock drop quick from any to {ip}" for ip in ips]) or "# no blocked devices"
    def apply(self, blocked_ips: list[str], *, apply: bool = False) -> FirewallResult:
        ips = normalize_local_ips(blocked_ips); rules = self.preview(ips)
        if not apply: return FirewallResult(self.name, False, tuple(ips), "dry-run", rules)
        pfctl = shutil.which("pfctl") or "/sbin/pfctl"
        check = _run([pfctl, "-n", "-f", "-"], input_text=rules)
        if check.returncode != 0: raise RuntimeError(f"PF validation failed: {check.stderr.strip()}")
        result = _run([pfctl, "-a", self.anchor, "-f", "-"], input_text=rules)
        if result.returncode != 0: raise RuntimeError(f"PF apply failed: {result.stderr.strip()}")
        _run([pfctl, "-e"])
        return FirewallResult(self.name, True, tuple(ips), "NetFather PF anchor applied", rules)
    def rollback(self, *, apply: bool = False) -> FirewallResult:
        cmd = f"pfctl -a {self.anchor} -F rules"
        if not apply: return FirewallResult(self.name, False, (), "dry-run rollback", cmd)
        pfctl = shutil.which("pfctl") or "/sbin/pfctl"
        result = _run([pfctl, "-a", self.anchor, "-F", "rules"])
        if result.returncode != 0: raise RuntimeError(result.stderr.strip())
        return FirewallResult(self.name, True, (), "NetFather PF anchor cleared")

class NullFirewallBackend(FirewallBackend):
    name = "none"
    def preview(self, blocked_ips: list[str]) -> str: return "Firewall enforcement disabled"
    def apply(self, blocked_ips: list[str], *, apply: bool = False) -> FirewallResult:
        return FirewallResult(self.name, False, tuple(normalize_local_ips(blocked_ips)), "disabled")
    def rollback(self, *, apply: bool = False) -> FirewallResult: return FirewallResult(self.name, False, (), "disabled")

def get_firewall_backend(name: str = "auto", platform_name: str | None = None) -> FirewallBackend:
    normalized = name.strip().lower()
    if normalized == "none": return NullFirewallBackend()
    if normalized == "nftables": return NftablesBackend()
    if normalized == "windows": return WindowsFirewallBackend()
    if normalized == "pf": return PfBackend()
    family = platform_family(platform_name)
    if family is PlatformFamily.LINUX: return NftablesBackend()
    if family is PlatformFamily.WINDOWS: return WindowsFirewallBackend()
    if family is PlatformFamily.MACOS: return PfBackend()
    return NullFirewallBackend()
