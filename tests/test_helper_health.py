from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient

from thinkific_tutor import helper_catalog, helper_router


def test_expired_helper_evidence_is_visible_to_monitoring(monkeypatch) -> None:
    fetched_at = (datetime.now(UTC) - timedelta(days=20)).isoformat()
    monkeypatch.setattr(
        helper_catalog, "pages_payload", lambda: {"pages": [{"fetched_at": fetched_at}]}
    )
    monkeypatch.setattr(helper_catalog, "_fresh_pages", lambda: ())
    app = FastAPI()
    app.include_router(helper_router.router)
    response = TestClient(app).get("/api/helper/healthz")

    assert response.status_code == 200
    assert response.json()["status"] == "degraded"
    assert response.json()["catalog"]["fresh"] is False
    assert response.json()["catalog"]["expiresInDays"] < 0


def test_fresh_helper_evidence_reports_refresh_headroom(monkeypatch) -> None:
    fetched_at = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    monkeypatch.setattr(
        helper_catalog, "pages_payload", lambda: {"pages": [{"fetched_at": fetched_at}]}
    )
    monkeypatch.setattr(helper_catalog, "_fresh_pages", lambda: ({}, {}))
    state = helper_catalog.freshness()

    assert state["fresh"] is True
    assert state["evidencePages"] == 2
    assert state["expiresInDays"] == 13
