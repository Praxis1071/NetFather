"""Linux runtime information and application paths."""
from __future__ import annotations

import os
import platform
from pathlib import Path
from typing import Mapping

PLATFORM = "linux"


def platform_name(_platform_name: str | None = None) -> str:
    return PLATFORM


def get_platform_info(_platform_name: str | None = None) -> dict[str, str]:
    return {"family": PLATFORM, "system": "Linux", "release": platform.release(), "machine": platform.machine() or "unknown-arch", "network_backend": "iproute2"}


def default_config_home(_platform_name: str | None = None, environ: Mapping[str, str] | None = None, home: Path | None = None) -> Path:
    env = os.environ if environ is None else environ
    home_dir = Path.home() if home is None else Path(home)
    value = env.get("XDG_CONFIG_HOME")
    return Path(value).expanduser() if value else home_dir / ".config"


def default_data_home(_platform_name: str | None = None, environ: Mapping[str, str] | None = None, home: Path | None = None) -> Path:
    env = os.environ if environ is None else environ
    home_dir = Path.home() if home is None else Path(home)
    value = env.get("XDG_DATA_HOME")
    return Path(value).expanduser() if value else home_dir / ".local" / "share"


def default_config_dir(_platform_name: str | None = None) -> Path:
    return default_config_home() / "netfather"


def default_data_dir(_platform_name: str | None = None) -> Path:
    return default_data_home() / "netfather"


def apply_private_mode(path: Path, mode: int) -> None:
    try:
        os.chmod(path, mode)
    except OSError:
        pass
