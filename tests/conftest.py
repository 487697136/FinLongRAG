"""Pytest fixtures shared across the test suite."""

from __future__ import annotations

import os

# Allow Settings.from_file() and app startup without a local .env file.
os.environ.setdefault(
    "FINLONGRAG_DATABASE_URL",
    "postgresql://finlongrag:finlongrag@127.0.0.1:5432/finlongrag_test",
)
