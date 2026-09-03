#!/usr/bin/env python3
"""Create release archives around a native PyInstaller executable."""

from __future__ import annotations

import argparse
import shutil
import stat
import tarfile
import tempfile
import zipfile
from pathlib import Path

TARGETS = {
    "windows-x64": ("netfather.exe", "NetFather-windows-x64.zip"),
    "windows-arm64": ("netfather.exe", "NetFather-windows-arm64.zip"),
    "linux-x64": ("netfather", "NetFather-linux-x64.tar.gz"),
    "linux-arm64": ("netfather", "NetFather-linux-arm64.tar.gz"),
    "macos-x64": ("netfather", "NetFather-macos-x64.tar.gz"),
    "macos-arm64": ("netfather", "NetFather-macos-arm64.tar.gz"),
}


def _copy_payload(root: Path, payload: Path, binary_name: str) -> None:
    payload.mkdir(parents=True, exist_ok=True)
    binary = root / "dist" / binary_name
    if not binary.is_file():
        raise SystemExit(f"Built executable not found: {binary}")
    target_binary = payload / binary_name
    shutil.copy2(binary, target_binary)
    if binary_name != "netfather.exe":
        target_binary.chmod(target_binary.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    for filename in ("README.md", "RELEASES.md", "LICENSE"):
        source = root / filename
        if source.is_file():
            shutil.copy2(source, payload / filename)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", choices=sorted(TARGETS), required=True)
    parser.add_argument("--output-dir", default="release")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent
    binary_name, archive_name = TARGETS[args.target]
    output_dir = root / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    archive_path = output_dir / archive_name

    with tempfile.TemporaryDirectory(prefix="netfather-release-") as temp_dir:
        payload = Path(temp_dir) / "NetFather"
        _copy_payload(root, payload, binary_name)
        if archive_name.endswith(".zip"):
            with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for path in sorted(payload.rglob("*")):
                    if path.is_file():
                        archive.write(path, path.relative_to(payload.parent))
        else:
            with tarfile.open(archive_path, "w:gz") as archive:
                archive.add(payload, arcname="NetFather")

    print(archive_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
