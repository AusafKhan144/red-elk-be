import uuid
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
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


@router.get("/analytics", response_model=AnalyticsOut)
async def admin_analytics(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    # Total and completed session counts
    total = await db.scalar(select(func.count()).select_from(AssessmentSession))
    completed = await db.scalar(
        select(func.count()).select_from(AssessmentSession)
        .where(AssessmentSession.status == SessionStatus.completed)
    )

    # Sessions by tier
    tier_rows = await db.execute(
        select(AssessmentSession.tier_at_time, func.count())
        .group_by(AssessmentSession.tier_at_time)
    )
    sessions_by_tier = {row[0].value: row[1] for row in tier_rows}

    # Average overall score
    avg_score = await db.scalar(select(func.avg(Report.overall_score)))

    # Average score per dimension across all completed sessions
    dim_rows = await db.execute(
        select(Response.dimension_id, func.avg(Response.answer_value))
        .join(AssessmentSession, Response.session_id == AssessmentSession.id)
        .where(AssessmentSession.status == SessionStatus.completed)
        .group_by(Response.dimension_id)
    )

    # Try to resolve dimension names from published assessments
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


@router.get("/users", response_model=list[UserProfile])
async def admin_list_users(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    return [UserProfile.model_validate(u) for u in result.scalars().all()]


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
        # Derive slug/name defaults from filename if not supplied
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
