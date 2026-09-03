#!/usr/bin/env python3
"""Fail a release build when the Python/runtime architecture is unexpected."""

from __future__ import annotations

import argparse
import platform


def normalize_machine(value: str) -> str:
    normalized = value.strip().lower().replace("-", "_")
    if normalized in {"x86_64", "amd64", "x64"}:
        return "x64"
    if normalized in {"aarch64", "arm64", "arm64e"}:
        return "arm64"
    return normalized or "unknown"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected", choices=("x64", "arm64"), required=True)
    args = parser.parse_args()

    raw = platform.machine()
    actual = normalize_machine(raw)
    if actual != args.expected:
        raise SystemExit(
            f"Architecture mismatch: expected {args.expected}, got {raw!r} (normalized={actual})"
        )
    print(f"Architecture check OK: {raw} -> {actual}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
