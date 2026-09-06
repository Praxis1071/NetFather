#!/usr/bin/env python3
"""Create the Linux GTK4 release archive around the native executable."""
from __future__ import annotations

import shutil
import stat
import tarfile
import tempfile
from pathlib import Path

TARGETS = {"linux-x64": ("netfather", "NetFather-linux-x64.tar.gz"), "linux-arm64": ("netfather", "NetFather-linux-arm64.tar.gz")}


def main() -> int:
    import argparse
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
        payload.mkdir()
        binary = root / "dist" / binary_name
        if not binary.is_file():
            raise SystemExit(f"Built executable not found: {binary}")
        target_binary = payload / binary_name
        shutil.copy2(binary, target_binary)
        target_binary.chmod(target_binary.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        for filename in ("README.md", "RELEASES.md", "LICENSE"):
            source = root / filename
            if source.is_file():
                shutil.copy2(source, payload / filename)
        with tarfile.open(archive_path, "w:gz") as archive:
            archive.add(payload, arcname="NetFather")
    print(archive_path)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
