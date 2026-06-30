"""Cross-process exclusive file lock via atomic lock-file creation."""

from __future__ import annotations

import os
import time
from contextlib import contextmanager
from collections.abc import Iterator
from pathlib import Path


@contextmanager
def exclusive_file_lock(lock_path: Path, *, timeout: float = 120.0) -> Iterator[None]:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout
    fd: int | None = None
    while True:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_RDWR)
            break
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise TimeoutError(f"timed out waiting for lock: {lock_path}") from None
            time.sleep(0.05)
    try:
        yield
    finally:
        if fd is not None:
            os.close(fd)
        lock_path.unlink(missing_ok=True)
