"""Cooperative cancellation and bounded child-process ownership."""
from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from concurrent.futures import CancelledError


class CancellationToken:
    def __init__(self) -> None:
        self._cancelled = threading.Event()

    @property
    def cancelled(self) -> bool:
        return self._cancelled.is_set()

    def cancel(self) -> None:
        self._cancelled.set()

    def check(self) -> None:
        if self.cancelled:
            raise CancelledError("Operation cancelled; previous device state was preserved.")


def run_process(args: list[str], *, token: CancellationToken | None = None, **kwargs) -> subprocess.CompletedProcess:
    """Retain subprocess.run semantics, reaping cancelled/timed-out children."""
    if token is None:
        return subprocess.run(args, **kwargs)
    token.check()
    timeout = kwargs.pop("timeout", None)
    input_text = kwargs.pop("input", None)
    check = kwargs.pop("check", False)
    if kwargs.pop("capture_output", False):
        kwargs.update(stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if input_text is not None:
        kwargs["stdin"] = subprocess.PIPE
    with subprocess.Popen(args, start_new_session=(os.name == "posix"), **kwargs) as process:
        started = time.monotonic()
        first = True
        try:
            while True:
                token.check()
                remaining = None if timeout is None else timeout - (time.monotonic() - started)
                if remaining is not None and remaining <= 0:
                    raise subprocess.TimeoutExpired(args, timeout)
                try:
                    stdout, stderr = process.communicate(input=input_text if first else None,
                                                         timeout=min(0.1, remaining) if remaining is not None else 0.1)
                    break
                except subprocess.TimeoutExpired:
                    first = False
        except BaseException:
            try:
                if os.name == "posix":
                    os.killpg(process.pid, signal.SIGKILL)
                else:
                    process.kill()
            except ProcessLookupError:
                pass
            process.communicate()
            raise
        token.check()
        result = subprocess.CompletedProcess(args, process.returncode, stdout, stderr)
        if check:
            result.check_returncode()
        return result
