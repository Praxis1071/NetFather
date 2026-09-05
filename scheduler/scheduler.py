"""Rule scheduler and firewall enforcement loop."""
from __future__ import annotations
import threading
import time
from core.config import Config
from core.database import Database
from firewall.engine import FirewallEngine

class RuleScheduler:
    def __init__(self, db: Database, config: Config | None = None) -> None:
        self.db = db; self.config = config or Config(); self._stop = threading.Event()
    def run_once(self, *, apply: bool | None = None):
        return FirewallEngine(self.db, self.config).sync(apply=apply)
    def start(self, *, interval_seconds: int | None = None, apply: bool | None = None,
              max_iterations: int | None = None) -> None:
        interval = interval_seconds or self.config.daemon.interval_seconds
        iterations = 0; self._stop.clear()
        while not self._stop.is_set():
            self.run_once(apply=apply); iterations += 1
            if max_iterations is not None and iterations >= max_iterations: break
            self._stop.wait(interval)
    def stop(self) -> None: self._stop.set()
