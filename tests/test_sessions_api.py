"""API tests for the session lifecycle and the enriched GET /sessions payload."""
import asyncio

import pytest

import app.routers.sessions as sessions_router

FREE_ANSWERS = [("s1", "strategy", 5), ("s2", "strategy", 3),
                ("d1", "data", 1), ("d2", "data", 2)]


async def _start(client, slug="test-assessment"):
    resp = await client.post("/sessions/start", json={"assessment_slug": slug})
    assert resp.status_code == 201
    return resp.json()["id"]


async def _answer(client, session_id, answers):
    for qid, dim, value in answers:
        resp = await client.post(
            f"/sessions/{session_id}/answer",
            json={"question_id": qid, "dimension_id": dim, "answer_value": value},
        )
        assert resp.status_code == 200


async def _submit(client, session_id):
    resp = await client.post(f"/sessions/{session_id}/submit")
    assert resp.status_code == 200
    # let the fire-and-forget PDF task finish before assertions
    if sessions_router._background_tasks:
        await asyncio.gather(*sessions_router._background_tasks)
    return resp.json()


async def test_full_lifecycle(client, assessment):
    session_id = await _start(client)
    await _answer(client, session_id, FREE_ANSWERS)
    body = await _submit(client, session_id)
    assert body["ok"] is True
    assert "report_id" in body


async def test_submit_twice_conflicts(client, assessment):
    session_id = await _start(client)
    await _answer(client, session_id, FREE_ANSWERS)
    await _submit(client, session_id)
    resp = await client.post(f"/sessions/{session_id}/submit")
    assert resp.status_code == 409


async def test_answer_is_idempotent_upsert(client, assessment):
    session_id = await _start(client)
    await _answer(client, session_id, [("s1", "strategy", 1)])
    await _answer(client, session_id, [("s1", "strategy", 5)])  # overwrite
    resp = await client.get(f"/sessions/{session_id}/answers")
    answers = resp.json()
    assert len(answers) == 1
    assert answers[0]["answer_value"] == 5


# ── GET /sessions enrichment ─────────────────────────────────────────────────

async def test_list_sessions_in_progress_has_progress_pct(client, assessment):
    session_id = await _start(client)
    await _answer(client, session_id, FREE_ANSWERS[:2])  # 2 of 4 free questions

    resp = await client.get("/sessions")
    [s] = resp.json()
    assert s["id"] == session_id
    assert s["status"] == "in_progress"
    assert s["progress_pct"] == 50
    assert s["score"] is None
    assert s["tier_result"] is None
    assert s["dimension_scores"] is None


async def test_list_sessions_completed_has_score_and_dimensions(client, assessment):
    session_id = await _start(client)
    await _answer(client, session_id, FREE_ANSWERS)
    await _submit(client, session_id)

    resp = await client.get("/sessions")
    [s] = resp.json()
    assert s["status"] == "completed"
    assert s["score"] == pytest.approx(60.0)
    assert s["tier_result"] == "maturing"
    assert s["progress_pct"] is None
    dims = {p["dimension"]: p for p in s["dimension_scores"]}
    assert dims["strategy"]["score"] == pytest.approx(80.0)
    assert dims["strategy"]["label"] == "Strategy & Vision"
    assert s["assessment_name"] == "Test Assessment"
    assert s["assessment_slug"] == "test-assessment"


async def test_list_sessions_progress_capped_at_100(client, assessment):
    session_id = await _start(client)
    # answer a premium question too — more answers than free-accessible questions
    await _answer(client, session_id, FREE_ANSWERS + [("s5", "strategy", 5)])

    resp = await client.get("/sessions")
    [s] = resp.json()
    assert s["progress_pct"] == 100


async def test_background_pdf_sets_pdf_url(client, assessment, mock_pdf):
    session_id = await _start(client)
    await _answer(client, session_id, FREE_ANSWERS)
    await _submit(client, session_id)

    mock_pdf.assert_awaited_once()
    resp = await client.get(f"/reports/{session_id}")
    assert resp.json()["pdf_url"] == "https://res.cloudinary.test/report.pdf"
