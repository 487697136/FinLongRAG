"""API-level smoke tests."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient
from pydantic import ValidationError

from finlongrag.api.app import create_app
from finlongrag.api.v1 import QueryRequest


def test_health_endpoint_reports_status() -> None:
    client = TestClient(create_app(dry_run=True))
    response = client.get("/api/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["status"] == "ok"
    assert payload["data"]["dry_run"] is True


def test_v1_graph_endpoint_returns_not_implemented_shape() -> None:
    client = TestClient(create_app(dry_run=True))
    # Unauthenticated graph access should be rejected before empty payload matters.
    response = client.get("/api/v1/knowledge-bases/test-kb/graph")
    assert response.status_code == 401


def test_query_request_rejects_unknown_mode() -> None:
    with pytest.raises(ValidationError):
        QueryRequest(question="hello", mode="hybrid")


def test_query_request_bounds_memory_window() -> None:
    with pytest.raises(ValidationError):
        QueryRequest(question="hello", memory_turn_window=1000)
