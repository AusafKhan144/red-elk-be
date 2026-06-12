import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies import get_current_user
from app.models.models import AssessmentSession, Report, User
from app.schemas.schemas import ReportOut
from app.services import report_builder

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/{session_id}", response_model=ReportOut)
async def get_report(
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await db.get(AssessmentSession, session_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    if session.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    out = await report_builder.get_report_out(session_id, db)
    if not out:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not yet generated")
    out.previous_radar_data = await report_builder.get_previous_radar_data(session, db)
    return out


@router.get("/{session_id}/pdf")
async def get_pdf(
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Redirect to the Cloudinary PDF URL. Triggers generation if not yet available."""
    session = await db.get(AssessmentSession, session_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    if session.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    report = await db.scalar(select(Report).where(Report.session_id == session_id))
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not yet generated")

    if not report.pdf_url:
        # Generate on demand if background task hasn't finished
        from app.models.models import Assessment
        from app.services.pdf import generate_and_upload_pdf

        try:
            report_out = await report_builder.get_report_out(session_id, db)
            if report_out is None:
                raise RuntimeError(f"Report row exists but could not be loaded for {session_id}")
            assessment = await db.get(Assessment, session.assessment_id)
            url = await generate_and_upload_pdf(report_out, assessment.name if assessment else "Assessment")
            report.pdf_url = url
            await db.commit()
        except Exception:
            logger.exception("On-demand PDF generation failed for session %s", session_id)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="PDF generation failed — please try again later",
            )

    if not report.pdf_url:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="PDF is not available for this report",
        )

    return RedirectResponse(url=report.pdf_url, status_code=302)
