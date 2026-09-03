from __future__ import annotations

from pathlib import Path

from core.platform import (
    PlatformFamily,
    default_config_home,
    default_data_home,
    platform_family,
)


def test_platform_family_normalization() -> None:
    assert platform_family("linux") is PlatformFamily.LINUX
    assert platform_family("win32") is PlatformFamily.WINDOWS
    assert platform_family("darwin") is PlatformFamily.MACOS
    assert platform_family("freebsd14") is PlatformFamily.OTHER


def test_windows_native_paths() -> None:
    env = {"APPDATA": r"C:\Users\Test\AppData\Roaming", "LOCALAPPDATA": r"C:\Users\Test\AppData\Local"}
    assert default_config_home("win32", env, Path("C:/Users/Test")) == Path(env["APPDATA"])
    assert default_data_home("win32", env, Path("C:/Users/Test")) == Path(env["LOCALAPPDATA"])


def test_macos_native_paths() -> None:
    home = Path("/Users/test")
    assert default_config_home("darwin", {}, home) == home / "Library" / "Application Support"
    assert default_data_home("darwin", {}, home) == home / "Library" / "Application Support"


def test_xdg_overrides_take_precedence_on_every_platform() -> None:
    env = {"XDG_CONFIG_HOME": "/tmp/cfg", "XDG_DATA_HOME": "/tmp/data"}
    assert default_config_home("win32", env, Path("/home/test")) == Path("/tmp/cfg")
    assert default_data_home("darwin", env, Path("/home/test")) == Path("/tmp/data")
