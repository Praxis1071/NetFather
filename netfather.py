#!/usr/bin/env python3
"""
NetFather - Yerel ağ cihaz ve erişim yönetim aracı.

Kullanım:
    python netfather.py --help
    python netfather.py status
    python netfather.py device list
"""

from __future__ import annotations

from cli.main import run

if __name__ == "__main__":
    run()
