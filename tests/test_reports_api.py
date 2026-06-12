"""API tests for GET /reports/:id (previous_radar_data) and the PDF endpoint."""
import uuid
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.models.models import Report
from tests.test_sessions_api import FREE_ANSWERS, _answer, _start, _submit


async def _complete_session(client, answers=FREE_ANSWERS):
    session_id = await _start(client)
    await _answer(client, session_id, answers)
    await _submit(client, session_id)
    return session_id


async def test_report_404_before_submit(client, assessment):
    session_id = await _start(client)
    resp = await client.get(f"/reports/{session_id}")
    assert resp.status_code == 404


async def test_report_payload(client, assessment):
    session_id = await _complete_session(client)
    resp = await client.get(f"/reports/{session_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["overall_score"] == pytest.approx(60.0)
    assert body["tier_result"] == "maturing"
    assert body["recommendations"]["strategy"] == "strategy-maturing"
    assert {p["dimension"] for p in body["radar_data"]} == {"strategy", "data"}
    assert body["previous_radar_data"] is None


async def test_previous_radar_data_from_prior_session(client, assessment):
    first = await _complete_session(
        client, [("s1", "strategy", 5), ("s2", "strategy", 5),
                 ("d1", "data", 5), ("d2", "data", 5)])
    second = await _complete_session(client)

    resp = await client.get(f"/reports/{second}")
    body = resp.json()
    prev = {p["dimension"]: p["score"] for p in body["previous_radar_data"]}
    assert prev["strategy"] == pytest.approx(100.0)
    assert prev["data"] == pytest.approx(100.0)

    # first session still has no predecessor
    resp = await client.get(f"/reports/{first}")
    assert resp.json()["previous_radar_data"] is None


# ── PDF endpoint ─────────────────────────────────────────────────────────────

async def test_pdf_404_without_report(client, assessment):
    session_id = await _start(client)
    resp = await client.get(f"/reports/{session_id}/pdf")
    assert resp.status_code == 404


async def test_pdf_redirects_when_url_set(client, assessment):
    session_id = await _complete_session(client)  # background task sets pdf_url
    resp = await client.get(f"/reports/{session_id}/pdf")
    assert resp.status_code == 302
    assert resp.headers["location"] == "https://res.cloudinary.test/report.pdf"


async def test_pdf_generated_on_demand_when_missing(client, db, assessment, monkeypatch):
    session_id = await _complete_session(client)
    report = await db.scalar(select(Report).where(Report.session_id == uuid.UUID(session_id)))
    report.pdf_url = None
    await db.commit()

    on_demand = AsyncMock(return_value="https://res.cloudinary.test/on-demand.pdf")
    monkeypatch.setattr("app.services.pdf.generate_and_upload_pdf", on_demand)

    resp = await client.get(f"/reports/{session_id}/pdf")
    assert resp.status_code == 302
    assert resp.headers["location"] == "https://res.cloudinary.test/on-demand.pdf"
    on_demand.assert_awaited_once()


async def test_pdf_502_when_generation_fails(client, db, assessment, monkeypatch):
    session_id = await _complete_session(client)
    report = await db.scalar(select(Report).where(Report.session_id == uuid.UUID(session_id)))
    report.pdf_url = None
    await db.commit()

    failing = AsyncMock(side_effect=RuntimeError("Cloudinary not configured"))
    monkeypatch.setattr("app.services.pdf.generate_and_upload_pdf", failing)

    resp = await client.get(f"/reports/{session_id}/pdf")
    assert resp.status_code == 502
