"""Tests for report_builder: build_report, radar helpers, previous radar, maturity summary."""
import uuid
from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from app.models.models import AssessmentSession, Report, Response, SessionStatus, TierEnum
from app.services import report_builder


async def _make_completed_session(db, user, assessment, completed_at, answers=None):
    session = AssessmentSession(
        id=uuid.uuid4(),
        user_id=user.id,
        assessment_id=assessment.id,
        status=SessionStatus.completed,
        tier_at_time=TierEnum.free,
        completed_at=completed_at,
    )
    db.add(session)
    for qid, dim, value in (answers or []):
        db.add(Response(
            id=uuid.uuid4(), session_id=session.id,
            question_id=qid, dimension_id=dim, answer_value=Decimal(str(value)),
        ))
    await db.commit()
    return session


DEFAULT_ANSWERS = [("s1", "strategy", 5), ("s2", "strategy", 3),
                   ("d1", "data", 1), ("d2", "data", 2)]


# ── build_report ─────────────────────────────────────────────────────────────

async def test_build_report_persists_and_scores(db, user, assessment):
    session = await _make_completed_session(
        db, user, assessment, datetime(2026, 1, 1), DEFAULT_ANSWERS)

    out = await report_builder.build_report(session.id, db)

    assert out.overall_score == pytest.approx(60.0)
    assert out.tier_result == "maturing"
    assert {p.dimension for p in out.radar_data} == {"strategy", "data"}
    labels = {p.dimension: p.label for p in out.radar_data}
    assert labels["strategy"] == "Strategy & Vision"
    assert out.recommendations["strategy"] == "strategy-maturing"

    # persisted
    report = await db.get(Report, out.id)
    assert report is not None
    assert float(report.overall_score) == pytest.approx(60.0)


async def test_build_report_is_idempotent(db, user, assessment):
    session = await _make_completed_session(
        db, user, assessment, datetime(2026, 1, 1), DEFAULT_ANSWERS)

    first = await report_builder.build_report(session.id, db)
    second = await report_builder.build_report(session.id, db)
    assert first.id == second.id
    assert second.overall_score == pytest.approx(60.0)


async def test_build_report_unknown_session_raises(db):
    with pytest.raises(ValueError):
        await report_builder.build_report(uuid.uuid4(), db)


# ── build_radar_data ─────────────────────────────────────────────────────────

def test_build_radar_data_labels_from_config(config):
    radar = report_builder.build_radar_data({"strategy": 80.0, "unknown": 10.0}, config)
    by_dim = {p.dimension: p for p in radar}
    assert by_dim["strategy"].label == "Strategy & Vision"
    assert by_dim["strategy"].score == 80.0
    assert by_dim["unknown"].label == "unknown"  # fallback to id


def test_build_radar_data_handles_empty():
    assert report_builder.build_radar_data({}, {}) == []
    assert report_builder.build_radar_data(None, None) == []


# ── get_previous_radar_data ──────────────────────────────────────────────────

async def test_previous_radar_none_without_prior(db, user, assessment):
    session = await _make_completed_session(
        db, user, assessment, datetime(2026, 1, 2), DEFAULT_ANSWERS)
    await report_builder.build_report(session.id, db)

    assert await report_builder.get_previous_radar_data(session, db) is None


async def test_previous_radar_returns_prior_scores(db, user, assessment):
    prior = await _make_completed_session(
        db, user, assessment, datetime(2026, 1, 1),
        [("s1", "strategy", 5), ("s2", "strategy", 5)])
    await report_builder.build_report(prior.id, db)

    current = await _make_completed_session(
        db, user, assessment, datetime(2026, 1, 2), DEFAULT_ANSWERS)
    await report_builder.build_report(current.id, db)

    radar = await report_builder.get_previous_radar_data(current, db)
    assert radar is not None
    by_dim = {p.dimension: p.score for p in radar}
    assert by_dim["strategy"] == pytest.approx(100.0)


async def test_previous_radar_picks_most_recent_prior(db, user, assessment):
    oldest = await _make_completed_session(
        db, user, assessment, datetime(2026, 1, 1),
        [("s1", "strategy", 1), ("s2", "strategy", 1)])
    await report_builder.build_report(oldest.id, db)

    middle = await _make_completed_session(
        db, user, assessment, datetime(2026, 1, 5),
        [("s1", "strategy", 4), ("s2", "strategy", 4)])
    await report_builder.build_report(middle.id, db)

    current = await _make_completed_session(
        db, user, assessment, datetime(2026, 1, 10), DEFAULT_ANSWERS)
    await report_builder.build_report(current.id, db)

    radar = await report_builder.get_previous_radar_data(current, db)
    by_dim = {p.dimension: p.score for p in radar}
    assert by_dim["strategy"] == pytest.approx(80.0)  # from `middle`, not `oldest`


# ── get_maturity_summary ─────────────────────────────────────────────────────

async def test_maturity_summary_none_without_completed_sessions(db, user):
    assert await report_builder.get_maturity_summary(user.id, db) is None


async def test_maturity_summary_uses_latest_completed(db, user, assessment):
    old = await _make_completed_session(
        db, user, assessment, datetime(2026, 1, 1),
        [("s1", "strategy", 1), ("s2", "strategy", 1)])
    await report_builder.build_report(old.id, db)

    latest = await _make_completed_session(
        db, user, assessment, datetime(2026, 2, 1), DEFAULT_ANSWERS)
    await report_builder.build_report(latest.id, db)

    summary = await report_builder.get_maturity_summary(user.id, db)
    assert summary is not None
    assert summary.overall_score == pytest.approx(60.0)
    assert summary.tier_result == "maturing"
    assert summary.as_of_session_id == latest.id
    assert {p.dimension for p in summary.radar_data} == {"strategy", "data"}
