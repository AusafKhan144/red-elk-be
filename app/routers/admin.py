import csv
import io
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies import get_current_admin
from app.models.models import Assessment, AssessmentSession, Report, Response, SessionStatus, User
from app.schemas.schemas import (
    AdminSessionOut,
    AnalyticsOut,
    AssessmentImportOut,
    DimensionAnalytics,
    UserProfile,
    UserRoleUpdate,
    UserTierUpdate,
)
from app.services.xlsx_parser import parse_xlsx_to_assessment_config

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/sessions", response_model=list[AdminSessionOut])
async def admin_list_sessions(
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    result = await db.execute(
        select(AssessmentSession)
        .order_by(AssessmentSession.started_at.desc())
        .limit(limit)
        .offset(offset)
    )
    sessions = result.scalars().all()
    return [AdminSessionOut.model_validate(s) for s in sessions]


@router.get("/sessions/export")
async def export_sessions_csv(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    result = await db.execute(
        select(AssessmentSession).order_by(AssessmentSession.started_at.desc())
    )
    sessions = result.scalars().all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["session_id", "user_id", "assessment_id", "status", "tier_at_time", "started_at", "completed_at"])
    for s in sessions:
        writer.writerow([
            s.id, s.user_id, s.assessment_id,
            s.status.value, s.tier_at_time.value,
            s.started_at.isoformat() if s.started_at else "",
            s.completed_at.isoformat() if s.completed_at else "",
        ])

    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="sessions.csv"'},
    )


@router.get("/analytics", response_model=AnalyticsOut)
async def admin_analytics(
    from_date: Optional[datetime] = Query(None, alias="from"),
    to_date: Optional[datetime] = Query(None, alias="to"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    total_q = select(func.count()).select_from(AssessmentSession)
    if from_date:
        total_q = total_q.where(AssessmentSession.started_at >= from_date)
    if to_date:
        total_q = total_q.where(AssessmentSession.started_at <= to_date)
    total = await db.scalar(total_q)

    completed_q = (
        select(func.count()).select_from(AssessmentSession)
        .where(AssessmentSession.status == SessionStatus.completed)
    )
    if from_date:
        completed_q = completed_q.where(AssessmentSession.started_at >= from_date)
    if to_date:
        completed_q = completed_q.where(AssessmentSession.started_at <= to_date)
    completed = await db.scalar(completed_q)

    tier_q = select(AssessmentSession.tier_at_time, func.count()).group_by(AssessmentSession.tier_at_time)
    if from_date:
        tier_q = tier_q.where(AssessmentSession.started_at >= from_date)
    if to_date:
        tier_q = tier_q.where(AssessmentSession.started_at <= to_date)
    tier_rows = await db.execute(tier_q)
    sessions_by_tier = {row[0].value: row[1] for row in tier_rows}

    avg_score_q = (
        select(func.avg(Report.overall_score))
        .join(AssessmentSession, Report.session_id == AssessmentSession.id)
    )
    if from_date:
        avg_score_q = avg_score_q.where(AssessmentSession.started_at >= from_date)
    if to_date:
        avg_score_q = avg_score_q.where(AssessmentSession.started_at <= to_date)
    avg_score = await db.scalar(avg_score_q)

    dim_q = (
        select(Response.dimension_id, func.avg(Response.answer_value))
        .join(AssessmentSession, Response.session_id == AssessmentSession.id)
        .where(AssessmentSession.status == SessionStatus.completed)
        .group_by(Response.dimension_id)
    )
    if from_date:
        dim_q = dim_q.where(AssessmentSession.started_at >= from_date)
    if to_date:
        dim_q = dim_q.where(AssessmentSession.started_at <= to_date)
    dim_rows = await db.execute(dim_q)

    dim_name_map: dict[str, str] = {}
    assessments = (await db.execute(select(Assessment).where(Assessment.is_published.is_(True)))).scalars().all()
    for a in assessments:
        for dim in a.config.get("dimensions", []):
            dim_name_map[dim["id"]] = dim["name"]

    dimension_analytics = [
        DimensionAnalytics(
            dimension_id=row[0],
            dimension_name=dim_name_map.get(row[0], row[0]),
            avg_score=round(float(row[1]) if row[1] else 0.0, 2),
        )
        for row in dim_rows
    ]

    return AnalyticsOut(
        total_sessions=total or 0,
        completed_sessions=completed or 0,
        sessions_by_tier=sessions_by_tier,
        avg_overall_score=float(avg_score) if avg_score else None,
        dimensions=dimension_analytics,
    )


# ---------------------------------------------------------------------------
# Users — literal paths before parameterized {user_id} routes
# ---------------------------------------------------------------------------

@router.get("/users", response_model=list[UserProfile])
async def admin_list_users(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    return [UserProfile.model_validate(u) for u in result.scalars().all()]


@router.get("/users/export")
async def export_users_csv(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    users = result.scalars().all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["user_id", "email", "company", "tier", "role", "created_at"])
    for u in users:
        writer.writerow([
            u.id, u.email, u.company or "",
            u.tier.value, u.role,
            u.created_at.isoformat() if u.created_at else "",
        ])

    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="users.csv"'},
    )


@router.get("/users/{user_id}/sessions", response_model=list[AdminSessionOut])
async def admin_get_user_sessions(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    result = await db.execute(
        select(AssessmentSession)
        .where(AssessmentSession.user_id == user_id)
        .order_by(AssessmentSession.started_at.desc())
    )
    return [AdminSessionOut.model_validate(s) for s in result.scalars().all()]


@router.patch("/users/{user_id}/role", response_model=UserProfile)
async def update_user_role(
    user_id: uuid.UUID,
    body: UserRoleUpdate,
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(get_current_admin),
):
    if body.role not in ("admin", "user"):
        raise HTTPException(status_code=400, detail="role must be 'admin' or 'user'")
    if user_id == current_admin.id:
        raise HTTPException(status_code=400, detail="Cannot change your own role")
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.role = body.role
    await db.commit()
    await db.refresh(user)
    return UserProfile.model_validate(user)


@router.patch("/users/{user_id}/tier", response_model=UserProfile)
async def update_user_tier(
    user_id: uuid.UUID,
    body: UserTierUpdate,
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(get_current_admin),
):
    if user_id == current_admin.id:
        raise HTTPException(status_code=400, detail="Cannot change your own tier")
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.tier = body.tier
    await db.commit()
    await db.refresh(user)
    return UserProfile.model_validate(user)


@router.post("/assessments/from-xlsx", response_model=AssessmentImportOut)
async def import_assessment_from_xlsx(
    file: UploadFile = File(...),
    slug: Optional[str] = Form(None),
    name: Optional[str] = Form(None),
    description: Optional[str] = Form(""),
    publish: bool = Form(False),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    content_type = file.content_type or ""
    filename = file.filename or ""
    if not (
        "spreadsheet" in content_type
        or "excel" in content_type
        or filename.endswith(".xlsx")
        or filename.endswith(".xlsm")
    ):
        raise HTTPException(status_code=400, detail="File must be an Excel (.xlsx) file")

    file_bytes = await file.read()

    try:
        base = filename.rsplit(".", 1)[0] if filename else "assessment"
        import re
        final_slug = slug or re.sub(r"[^a-z0-9]+", "-", base.lower()).strip("-")
        final_name = name or base.replace("-", " ").replace("_", " ").title()

        config = parse_xlsx_to_assessment_config(
            file_bytes=file_bytes,
            slug=final_slug,
            name=final_name,
            description=description or "",
            is_published=publish,
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Failed to parse XLSX: {exc}")

    existing = await db.scalar(select(Assessment).where(Assessment.slug == final_slug))
    if existing:
        existing.config = config
        existing.name = final_name
        existing.version = existing.version + 1
        existing.is_published = publish
        await db.commit()
        await db.refresh(existing)
        return AssessmentImportOut.model_validate(existing)

    assessment = Assessment(
        slug=final_slug,
        name=final_name,
        config=config,
        is_published=publish,
        version=1,
    )
    db.add(assessment)
    await db.commit()
    await db.refresh(assessment)
    return AssessmentImportOut.model_validate(assessment)
