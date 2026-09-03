#!/usr/bin/env python3
"""Validate release tag/version consistency."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.version import VERSION


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", required=True, help="Release tag, e.g. v0.4.0")
    args = parser.parse_args()
    expected = f"v{VERSION}"
    if args.tag != expected:
        parser.error(f"tag/version mismatch: tag={args.tag!r}, expected={expected!r}")
    print(f"Version check OK: {args.tag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
