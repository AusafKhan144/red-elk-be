import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies import get_current_user
from app.models.models import Assessment, AssessmentSession, Report, Response, SessionStatus, User
from app.schemas.schemas import AnswerIn, SessionOut, SessionStartIn
from app.services import report_builder

router = APIRouter(prefix="/sessions", tags=["sessions"])


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
        existing.answer_value = body.answer_value
        existing.answered_at = datetime.now(timezone.utc)
    else:
        db.add(Response(
            id=uuid.uuid4(),
            session_id=session_id,
            question_id=body.question_id,
            dimension_id=body.dimension_id,
            answer_value=body.answer_value,
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

    # Kick off PDF generation in the background (non-blocking)
    import asyncio
    asyncio.create_task(_generate_pdf_background(report_out, session.assessment_id, db))

    return {"ok": True, "report_id": str(report_out.id)}


@router.get("", response_model=list[SessionOut])
async def list_sessions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AssessmentSession)
        .where(AssessmentSession.user_id == current_user.id)
        .order_by(AssessmentSession.started_at.desc())
    )
    sessions = result.scalars().all()
    return [SessionOut.model_validate(s) for s in sessions]


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


async def _generate_pdf_background(report_out, assessment_id, db: AsyncSession):
    """Fire-and-forget: generate PDF and update report.pdf_url."""
    try:
        from sqlalchemy import select
        from app.models.models import Assessment, Report
        from app.services.pdf import generate_and_upload_pdf

        assessment = await db.get(Assessment, assessment_id)
        url = await generate_and_upload_pdf(report_out, assessment.name if assessment else "Assessment")

        report = await db.scalar(select(Report).where(Report.session_id == report_out.session_id))
        if report:
            report.pdf_url = url
            await db.commit()
    except Exception:
        pass  # PDF failure must not break the submit flow
