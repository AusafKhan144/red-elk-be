"""
Builds and persists a Report from a completed AssessmentSession + ScoringResult.
Calls the scoring service, writes to the reports table, and optionally triggers PDF.
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.models import AssessmentSession, Report, Response, Assessment, SessionStatus
from app.schemas.schemas import MaturitySummary, RadarPoint, ReportOut
from app.services.scoring import score_responses, ScoringResult


async def build_report(session_id: uuid.UUID, db: AsyncSession) -> ReportOut:
    """
    Fetch all responses for a session, run scoring, persist a Report row,
    and return a fully populated ReportOut.
    Idempotent: if a report already exists for the session, return it.
    """
    # Return existing report if already built
    existing = await db.scalar(
        select(Report).where(Report.session_id == session_id)
    )
    if existing:
        return _to_report_out(existing, {})

    # Load session + assessment config
    session = await db.get(AssessmentSession, session_id)
    if not session:
        raise ValueError(f"Session {session_id} not found")

    assessment = await db.get(Assessment, session.assessment_id)
    if not assessment:
        raise ValueError(f"Assessment {session.assessment_id} not found")

    # Load responses
    result = await db.execute(
        select(Response).where(Response.session_id == session_id)
    )
    raw_responses = [
        {
            "question_id": r.question_id,
            "dimension_id": r.dimension_id,
            "answer_value": float(r.answer_value),
        }
        for r in result.scalars().all()
    ]

    scored: ScoringResult = score_responses(
        responses=raw_responses,
        config=assessment.config,
        tier=session.tier_at_time.value,
    )

    report = Report(
        id=uuid.uuid4(),
        session_id=session_id,
        scores=scored.dimension_scores,
        overall_score=scored.overall_score,
        tier_result=scored.tier_result,
        generated_at=datetime.now(timezone.utc),
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)

    return _to_report_out(report, scored)


def build_radar_data(scores: dict, config: dict) -> list[RadarPoint]:
    """Build radar points from a report's stored scores + dimension names in config."""
    names = {d["id"]: d.get("name", d["id"]) for d in (config or {}).get("dimensions", [])}
    return [
        RadarPoint(dimension=dim_id, score=float(score), label=names.get(dim_id, dim_id))
        for dim_id, score in (scores or {}).items()
    ]


async def get_previous_radar_data(
    session: AssessmentSession, db: AsyncSession
) -> list[RadarPoint] | None:
    """
    Radar data from the most recent completed session of the same assessment
    by the same user, prior to the given session. None if no such report exists.
    """
    if session.completed_at is None:
        return None
    prev = await db.scalar(
        select(AssessmentSession)
        .where(
            AssessmentSession.user_id == session.user_id,
            AssessmentSession.assessment_id == session.assessment_id,
            AssessmentSession.status == SessionStatus.completed,
            AssessmentSession.completed_at < session.completed_at,
            AssessmentSession.id != session.id,
        )
        .order_by(AssessmentSession.completed_at.desc())
        .limit(1)
    )
    if not prev:
        return None
    report = await db.scalar(select(Report).where(Report.session_id == prev.id))
    if not report:
        return None
    assessment = await db.get(Assessment, session.assessment_id)
    return build_radar_data(report.scores, assessment.config if assessment else {})


async def get_maturity_summary(user_id: uuid.UUID, db: AsyncSession) -> MaturitySummary | None:
    """Summary of the user's most recent completed session's report, or None."""
    row = (
        await db.execute(
            select(Report, AssessmentSession)
            .join(AssessmentSession, Report.session_id == AssessmentSession.id)
            .where(
                AssessmentSession.user_id == user_id,
                AssessmentSession.status == SessionStatus.completed,
            )
            .order_by(AssessmentSession.completed_at.desc())
            .limit(1)
        )
    ).first()
    if not row:
        return None
    report, session = row
    assessment = await db.get(Assessment, session.assessment_id)
    return MaturitySummary(
        overall_score=float(report.overall_score),
        tier_result=report.tier_result,
        radar_data=build_radar_data(report.scores, assessment.config if assessment else {}),
        as_of_session_id=session.id,
        as_of_date=session.completed_at,
    )


def _to_report_out(report: Report, scored) -> ReportOut:
    scores = report.scores or {}
    recommendations = {}
    radar_data = []

    if isinstance(scored, ScoringResult):
        recommendations = scored.recommendations
        radar_data = [
            RadarPoint(
                dimension=dim_id,
                score=score,
                label=scored.dimension_names.get(dim_id, dim_id),
            )
            for dim_id, score in scores.items()
        ]

    return ReportOut(
        id=report.id,
        session_id=report.session_id,
        scores=scores,
        overall_score=float(report.overall_score),
        tier_result=report.tier_result,
        recommendations=recommendations,
        radar_data=radar_data,
        pdf_url=report.pdf_url,
        generated_at=report.generated_at,
    )


async def get_report_out(session_id: uuid.UUID, db: AsyncSession) -> ReportOut | None:
    """Fetch and return an existing report, or None if not yet generated."""
    report = await db.scalar(
        select(Report).where(Report.session_id == session_id)
    )
    if not report:
        return None

    session = await db.get(AssessmentSession, session_id)
    assessment = await db.get(Assessment, session.assessment_id)

    result = await db.execute(
        select(Response).where(Response.session_id == session_id)
    )
    raw_responses = [
        {
            "question_id": r.question_id,
            "dimension_id": r.dimension_id,
            "answer_value": float(r.answer_value),
        }
        for r in result.scalars().all()
    ]

    scored: ScoringResult = score_responses(
        responses=raw_responses,
        config=assessment.config,
        tier=session.tier_at_time.value,
    )
    return _to_report_out(report, scored)
