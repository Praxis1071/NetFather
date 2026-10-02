"""Linux systemd service helpers for the NetFather daemon."""
from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class ServicePlan:
    family: str
    description: str
    command: str
    destination: str | None = None


def daemon_command() -> str:
    executable = Path(sys.executable).resolve()
    return f'"{executable}" -m scheduler.scheduler'


def service_plan() -> ServicePlan:
    command = daemon_command()
    unit = f"""[Unit]\nDescription=NetFather network policy daemon\nAfter=network-online.target\nWants=network-online.target\n\n[Service]\nType=simple\nExecStart={command}\nRestart=on-failure\nRestartSec=3\n\n[Install]\nWantedBy=multi-user.target\n"""
    return ServicePlan("linux", unit, command, "/etc/systemd/system/netfather.service")


def install_service(*, apply: bool = False) -> ServicePlan:
    plan = service_plan()
    if not apply:
        return plan
    dest = Path(plan.destination or "")
    dest.write_text(plan.description, encoding="utf-8")
    subprocess.run(["systemctl", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "enable", "--now", "netfather.service"], check=True)
    return plan


def uninstall_service(*, apply: bool = False) -> str:
    if not apply:
        return "dry-run uninstall (linux)"
    subprocess.run(["systemctl", "disable", "--now", "netfather.service"], check=False)
    Path("/etc/systemd/system/netfather.service").unlink(missing_ok=True)
    subprocess.run(["systemctl", "daemon-reload"], check=False)
    return "removed"


if __name__ == "__main__":
    raise SystemExit(subprocess.call(["systemctl", "start", "netfather.service"]))
