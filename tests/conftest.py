"""
Pytest ortak yapılandırması.

Proje bir paket olarak kurulmadan (`pip install -e .` yapılmadan) da
`pytest` doğrudan proje kökünden çalıştırılabilsin diye kök dizini
sys.path'e ekler.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
