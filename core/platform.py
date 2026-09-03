"""Cross-platform runtime detection and platform-native application paths."""

from __future__ import annotations

import os
import platform as _platform
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Mapping


class PlatformFamily(str, Enum):
    LINUX = "linux"
    WINDOWS = "windows"
    MACOS = "macos"
    OTHER = "other"


@dataclass(frozen=True)
class PlatformInfo:
    family: PlatformFamily
    system: str
    release: str
    machine: str
    supported: bool
    network_backend: str

    @property
    def label(self) -> str:
        machine = self.machine or "unknown-arch"
        return f"{self.system} {self.release} ({machine})".strip()


def platform_family(platform_name: str | None = None) -> PlatformFamily:
    """Normalize ``sys.platform``-style values into NetFather platform families."""
    value = (platform_name or sys.platform).lower()
    if value.startswith("linux"):
        return PlatformFamily.LINUX
    if value.startswith(("win32", "cygwin", "msys")) or value == "windows":
        return PlatformFamily.WINDOWS
    if value.startswith("darwin") or value in {"mac", "macos"}:
        return PlatformFamily.MACOS
    return PlatformFamily.OTHER


def get_platform_info(platform_name: str | None = None) -> PlatformInfo:
    family = platform_family(platform_name)
    system = {
        PlatformFamily.LINUX: "Linux",
        PlatformFamily.WINDOWS: "Windows",
        PlatformFamily.MACOS: "macOS",
        PlatformFamily.OTHER: _platform.system() or sys.platform,
    }[family]
    backend = {
        PlatformFamily.LINUX: "iproute2",
        PlatformFamily.WINDOWS: "PowerShell/Get-Net*",
        PlatformFamily.MACOS: "route/ipconfig/arp",
        PlatformFamily.OTHER: "socket fallback",
    }[family]
    return PlatformInfo(
        family=family,
        system=system,
        release=_platform.release(),
        machine=_platform.machine(),
        supported=family is not PlatformFamily.OTHER,
        network_backend=backend,
    )


def default_config_home(
    platform_name: str | None = None,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    """Return the platform-native base directory for NetFather configuration."""
    env = os.environ if environ is None else environ
    home_dir = Path.home() if home is None else Path(home)
    family = platform_family(platform_name)

    # XDG overrides remain honored everywhere for portable/dev environments.
    if env.get("XDG_CONFIG_HOME"):
        return Path(env["XDG_CONFIG_HOME"]).expanduser()

    if family is PlatformFamily.WINDOWS:
        base = env.get("APPDATA") or env.get("LOCALAPPDATA")
        return Path(base).expanduser() if base else home_dir / "AppData" / "Roaming"
    if family is PlatformFamily.MACOS:
        return home_dir / "Library" / "Application Support"
    return home_dir / ".config"


def default_data_home(
    platform_name: str | None = None,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    """Return the platform-native base directory for NetFather mutable data."""
    env = os.environ if environ is None else environ
    home_dir = Path.home() if home is None else Path(home)
    family = platform_family(platform_name)

    if env.get("XDG_DATA_HOME"):
        return Path(env["XDG_DATA_HOME"]).expanduser()

    if family is PlatformFamily.WINDOWS:
        base = env.get("LOCALAPPDATA") or env.get("APPDATA")
        return Path(base).expanduser() if base else home_dir / "AppData" / "Local"
    if family is PlatformFamily.MACOS:
        return home_dir / "Library" / "Application Support"
    return home_dir / ".local" / "share"


def default_config_dir(platform_name: str | None = None) -> Path:
    family = platform_family(platform_name)
    app_dir = "NetFather" if family in {PlatformFamily.WINDOWS, PlatformFamily.MACOS} else "netfather"
    return default_config_home(platform_name) / app_dir


def default_data_dir(platform_name: str | None = None) -> Path:
    family = platform_family(platform_name)
    app_dir = "NetFather" if family in {PlatformFamily.WINDOWS, PlatformFamily.MACOS} else "netfather"
    return default_data_home(platform_name) / app_dir


def apply_private_mode(path: Path, mode: int) -> None:
    """Apply POSIX owner-only permissions where meaningful; no-op on Windows."""
    if os.name == "nt":
        return
    try:
        os.chmod(path, mode)
    except OSError:
        # Filesystem ACLs or mounts may not implement POSIX chmod semantics.
        pass
