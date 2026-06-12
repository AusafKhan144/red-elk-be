"""API tests for GET /auth/me maturity_summary."""
import pytest

from tests.test_sessions_api import FREE_ANSWERS, _answer, _start, _submit


async def test_me_summary_null_without_sessions(client):
    resp = await client.get("/auth/me")
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == "test@example.com"
    assert body["maturity_summary"] is None


async def test_me_summary_from_latest_completed(client, assessment):
    session_id = await _start(client)
    await _answer(client, session_id, FREE_ANSWERS)
    await _submit(client, session_id)

    resp = await client.get("/auth/me")
    summary = resp.json()["maturity_summary"]
    assert summary is not None
    assert summary["overall_score"] == pytest.approx(60.0)
    assert summary["tier_result"] == "maturing"
    assert summary["as_of_session_id"] == session_id
    assert {p["dimension"] for p in summary["radar_data"]} == {"strategy", "data"}


async def test_me_summary_ignores_in_progress(client, assessment):
    await _start(client)  # never submitted
    resp = await client.get("/auth/me")
    assert resp.json()["maturity_summary"] is None
