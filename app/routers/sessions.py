import asyncio
import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import async_session_maker, get_db
from app.dependencies import get_current_user
from app.models.models import Assessment, AssessmentSession, Report, Response, SessionStatus, User
from app.schemas.schemas import AnswerIn, AnswerOut, ReportOut, SessionOut, SessionStartIn
from app.services import report_builder
from app.services.scoring import accessible_question_count

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sessions", tags=["sessions"])

# Strong references so fire-and-forget PDF tasks aren't garbage-collected mid-flight
_background_tasks: set[asyncio.Task] = set()


@router.post("/start", response_model=SessionOut, status_code=status.HTTP_201_CREATED)
async def start_session(
    body: SessionStartIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Start a new assessment session. Snapshots the user's current tier."""
    slug = body.assessment_slug

    result = await db.execute(
        select(Assessment).where(Assessment.slug == slug, Assessment.is_published.is_(True))
    )
    assessment = result.scalar_one_or_none()
    if not assessment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found")

    session = AssessmentSession(
        id=uuid.uuid4(),
        user_id=current_user.id,
        assessment_id=assessment.id,
        status=SessionStatus.in_progress,
        tier_at_time=current_user.tier,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return SessionOut.model_validate(session)


@router.post("/{session_id}/answer", response_model=dict)
async def answer_question(
    session_id: uuid.UUID,
    body: AnswerIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Record or update a single answer. Idempotent: re-submitting a question_id
    overwrites the previous answer.
    """
    session = await _get_owned_session(session_id, current_user, db)
    if session.status != SessionStatus.in_progress:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Session is not in progress")

    # Upsert: delete existing answer for this question, then insert
    existing = await db.scalar(
        select(Response).where(
            Response.session_id == session_id,
            Response.question_id == body.question_id,
        )
    )
    if existing:
        existing.answer_value = Decimal(str(body.answer_value))
        existing.answered_at = datetime.now(timezone.utc)
    else:
        db.add(Response(
            id=uuid.uuid4(),
            session_id=session_id,
            question_id=body.question_id,
            dimension_id=body.dimension_id,
            answer_value=Decimal(str(body.answer_value)),
        ))

    await db.commit()
    return {"ok": True}


@router.post("/{session_id}/submit", response_model=dict)
async def submit_session(
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Mark session completed, run scoring, generate report.
    Also triggers async PDF generation (fire-and-forget).
    """
    session = await _get_owned_session(session_id, current_user, db)
    if session.status != SessionStatus.in_progress:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Session already submitted or abandoned")

    session.status = SessionStatus.completed
    session.completed_at = datetime.now(timezone.utc)
    await db.commit()

    report_out = await report_builder.build_report(session_id, db)

    task = asyncio.create_task(_generate_pdf_background(report_out, session.assessment_id))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    return {"ok": True, "report_id": str(report_out.id)}


@router.get("/{session_id}/answers", response_model=list[AnswerOut])
async def get_session_answers(
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_owned_session(session_id, current_user, db)
    result = await db.execute(
        select(Response).where(Response.session_id == session_id)
    )
    return [AnswerOut.model_validate(r) for r in result.scalars().all()]


@router.patch("/{session_id}/abandon", response_model=dict)
async def abandon_session(
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await _get_owned_session(session_id, current_user, db)
    if session.status != SessionStatus.in_progress:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Session is not in progress")
    session.status = SessionStatus.abandoned
    await db.commit()
    return {"ok": True}


@router.get("", response_model=list[SessionOut])
async def list_sessions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AssessmentSession)
        .options(selectinload(AssessmentSession.assessment))
        .where(AssessmentSession.user_id == current_user.id)
        .order_by(AssessmentSession.started_at.desc())
    )
    sessions = result.scalars().all()
    session_ids = [s.id for s in sessions]

    reports_by_session: dict[uuid.UUID, Report] = {}
    answer_counts: dict[uuid.UUID, int] = {}
    if session_ids:
        reports = await db.execute(select(Report).where(Report.session_id.in_(session_ids)))
        reports_by_session = {r.session_id: r for r in reports.scalars().all()}

        in_progress_ids = [s.id for s in sessions if s.status == SessionStatus.in_progress]
        if in_progress_ids:
            counts = await db.execute(
                select(Response.session_id, func.count(Response.id))
                .where(Response.session_id.in_(in_progress_ids))
                .group_by(Response.session_id)
            )
            answer_counts = {sid: n for sid, n in counts.all()}

    out = []
    for s in sessions:
        data = SessionOut.model_validate(s)
        if s.assessment:
            data.assessment_name = s.assessment.name
            data.assessment_slug = s.assessment.slug

        report = reports_by_session.get(s.id)
        if report:
            data.score = float(report.overall_score)
            data.tier_result = report.tier_result
            if s.status == SessionStatus.completed and s.assessment:
                data.dimension_scores = report_builder.build_radar_data(
                    report.scores, s.assessment.config
                )

        if s.status == SessionStatus.in_progress and s.assessment:
            total = accessible_question_count(s.assessment.config, s.tier_at_time.value)
            if total > 0:
                data.progress_pct = min(round(answer_counts.get(s.id, 0) / total * 100), 100)
            else:
                data.progress_pct = 0

        out.append(data)
    return out


async def _get_owned_session(
    session_id: uuid.UUID,
    current_user: User,
    db: AsyncSession,
) -> AssessmentSession:
    session = await db.get(AssessmentSession, session_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    if session.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your session")
    return session


async def _generate_pdf_background(
    report_out: ReportOut,
    assessment_id: uuid.UUID,
) -> None:
    """Fire-and-forget: generate PDF and update report.pdf_url.

    Uses a fresh DB session — the request-scoped session is closed by the time
    this task runs. Failures are logged but never propagate (PDF must not break
    the submit flow).
    """
    try:
        from app.services.pdf import generate_and_upload_pdf

        async with async_session_maker() as db:
            assessment = await db.get(Assessment, assessment_id)
            url = await generate_and_upload_pdf(report_out, assessment.name if assessment else "Assessment")

            report = await db.scalar(select(Report).where(Report.session_id == report_out.session_id))
            if report:
                report.pdf_url = url
                await db.commit()
    except Exception:
        logger.exception("PDF generation failed for session %s", report_out.session_id)
