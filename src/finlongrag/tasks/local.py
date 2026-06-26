"""Local background task executor.

The project intentionally uses a local ThreadPoolExecutor for the first
Windows-friendly version. It keeps long-running document parsing and index
building outside request handlers without requiring Redis, Celery, or a
separate worker process.
"""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from threading import Lock
from typing import Any


class LocalTaskExecutor:
    def __init__(self, *, max_workers: int = 2) -> None:
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="finlongrag-task")
        self._futures: dict[str, Future[Any]] = {}
        self._lock = Lock()

    def submit(self, task_id: str, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Future[Any]:
        future = self._executor.submit(func, *args, **kwargs)
        with self._lock:
            self._futures[task_id] = future
        future.add_done_callback(lambda _: self._forget(task_id))
        return future

    def is_running(self, task_id: str) -> bool:
        with self._lock:
            future = self._futures.get(task_id)
        return bool(future and not future.done())

    def _forget(self, task_id: str) -> None:
        with self._lock:
            self._futures.pop(task_id, None)


_DEFAULT_EXECUTOR = LocalTaskExecutor()


def get_default_executor() -> LocalTaskExecutor:
    return _DEFAULT_EXECUTOR
