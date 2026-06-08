from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.dependencies import get_current_user
from app.models.models import Assessment, User
from app.schemas.schemas import AssessmentListItem, AssessmentOut, DimensionOut, QuestionOut

router = APIRouter(prefix="/assessments", tags=["assessments"])

_TIER_ORDER = {"free": 0, "basic": 1, "premium": 2}
_TIER_LIMITS = {"free": 2, "basic": 4, "premium": None}


@router.get("", response_model=list[AssessmentListItem])
async def list_assessments(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Assessment).where(Assessment.is_published.is_(True))
    )
    assessments = result.scalars().all()
    return [AssessmentListItem.model_validate(a) for a in assessments]


@router.get("/{slug}", response_model=AssessmentOut)
async def get_assessment(
    slug: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Assessment).where(Assessment.slug == slug, Assessment.is_published.is_(True))
    )
    assessment = result.scalar_one_or_none()
    if not assessment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found")

    return _build_assessment_out(assessment, current_user.tier.value)


def _build_assessment_out(assessment: Assessment, tier: str) -> AssessmentOut:
    user_level = _TIER_ORDER.get(tier, 0)
    limit = _TIER_LIMITS.get(tier)

    dimensions = []
    for dim in assessment.config.get("dimensions", []):
        eligible = [
            q for q in dim.get("questions", [])
            if _TIER_ORDER.get(q.get("tier", "free"), 0) <= user_level
        ]
        if limit is not None:
            eligible = eligible[:limit]

        dimensions.append(DimensionOut(
            id=dim["id"],
            name=dim["name"],
            weight=float(dim.get("weight", 1.0)),
            questions=[
                QuestionOut(
                    id=q["id"],
                    text=q["text"],
                    tier=q.get("tier", "free"),
                    type=q.get("type", "scale"),
                    options=q.get("options"),
                    max_score=float(q.get("max_score", 5)),
                )
                for q in eligible
            ],
        ))

    return AssessmentOut(
        id=assessment.id,
        slug=assessment.slug,
        name=assessment.name,
        description=assessment.description,
        version=assessment.version,
        dimensions=dimensions,
    )
