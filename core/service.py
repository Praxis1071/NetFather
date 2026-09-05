"""OS-native daemon/service installation helpers."""
from __future__ import annotations
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from core.platform import PlatformFamily, platform_family

@dataclass(frozen=True)
class ServicePlan:
    family: str
    description: str
    command: str
    destination: str | None = None


def daemon_command() -> str:
    executable = Path(sys.executable).resolve()
    if getattr(sys, "frozen", False):
        return f'"{executable}" daemon run --apply'
    return f'"{executable}" -m cli.main daemon run --apply'


def service_plan(platform_name: str | None = None) -> ServicePlan:
    family = platform_family(platform_name); command = daemon_command()
    if family is PlatformFamily.LINUX:
        unit = f"""[Unit]\nDescription=NetFather network policy daemon\nAfter=network-online.target\nWants=network-online.target\n\n[Service]\nType=simple\nExecStart={command}\nRestart=on-failure\nRestartSec=3\n\n[Install]\nWantedBy=multi-user.target\n"""
        return ServicePlan("linux", unit, command, "/etc/systemd/system/netfather.service")
    if family is PlatformFamily.WINDOWS:
        task = f'schtasks /Create /TN NetFather /SC ONSTART /RU SYSTEM /RL HIGHEST /TR "{command}" /F'
        return ServicePlan("windows", task, command, "Task Scheduler: NetFather")
    if family is PlatformFamily.MACOS:
        if getattr(sys, "frozen", False):
            args = [str(Path(sys.executable).resolve()), "daemon", "run", "--apply"]
        else:
            args = [str(Path(sys.executable).resolve()), "-m", "cli.main", "daemon", "run", "--apply"]
        arg_xml = "".join(f"<string>{item}</string>" for item in args)
        plist = f'''<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n<plist version="1.0"><dict><key>Label</key><string>xyz.netfather.daemon</string><key>ProgramArguments</key><array>{arg_xml}</array><key>RunAtLoad</key><true/><key>KeepAlive</key><true/></dict></plist>'''
        return ServicePlan("macos", plist, command, "/Library/LaunchDaemons/xyz.netfather.daemon.plist")
    return ServicePlan("other", "Unsupported platform", command)


def install_service(*, apply: bool = False) -> ServicePlan:
    plan = service_plan()
    if not apply or plan.family == "other": return plan
    if plan.family == "linux":
        dest = Path(plan.destination or "")
        dest.write_text(plan.description, encoding="utf-8")
        subprocess.run(["systemctl", "daemon-reload"], check=True)
        subprocess.run(["systemctl", "enable", "--now", "netfather.service"], check=True)
    elif plan.family == "windows":
        subprocess.run(plan.description, shell=True, check=True)
    elif plan.family == "macos":
        dest = Path(plan.destination or "")
        dest.write_text(plan.description, encoding="utf-8")
        subprocess.run(["launchctl", "bootstrap", "system", str(dest)], check=True)
    return plan


def uninstall_service(*, apply: bool = False) -> str:
    family = platform_family()
    if not apply: return f"dry-run uninstall ({family.value})"
    if family is PlatformFamily.LINUX:
        subprocess.run(["systemctl", "disable", "--now", "netfather.service"], check=False)
        Path("/etc/systemd/system/netfather.service").unlink(missing_ok=True)
        subprocess.run(["systemctl", "daemon-reload"], check=False)
    elif family is PlatformFamily.WINDOWS:
        subprocess.run(["schtasks", "/Delete", "/TN", "NetFather", "/F"], check=False)
    elif family is PlatformFamily.MACOS:
        path = Path("/Library/LaunchDaemons/xyz.netfather.daemon.plist")
        subprocess.run(["launchctl", "bootout", "system", str(path)], check=False)
        path.unlink(missing_ok=True)
    return "removed"
