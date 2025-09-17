from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional

from app.core.database import get_db
from app.services.assessment_service import AssessmentService
from app.schemas.assessment import Assessment, AssessmentSubmission, AssessmentSubmissionCreate
from app.api.deps import get_current_user, get_current_user_optional
from app.models.user import User,UserRoleEnum
from app.models.assessment import TierEnum
from app.schemas.assessment import AssessmentCreate

router = APIRouter()

@router.get("/", response_model=List[Assessment])
async def get_assessments(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    db: AsyncSession = Depends(get_db)
):
    """Get all available assessments"""
    service = AssessmentService(db)
    return await service.get_all_assessments(skip=skip, limit=limit)

@router.get("/{assessment_id}")
async def get_assessment(
    assessment_id: int,
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db)
):
    """Get assessment with questions filtered by user tier"""
    service = AssessmentService(db)
    
    # Determine user tier
    user_tier: TierEnum = TierEnum(current_user.tier) if current_user else TierEnum.FREE
    
    assessment = await service.get_assessment_for_user_tier(assessment_id, user_tier)
    
    if not assessment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assessment not found"
        )
    
    return assessment

@router.post("/{assessment_id}/submit", response_model=AssessmentSubmission)
async def submit_assessment(
    assessment_id: int,
    submission: AssessmentSubmissionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Submit assessment responses"""
    submission.assessment_id = assessment_id
    service = AssessmentService(db)
    return await service.submit_assessment_responses(submission, current_user.id)

@router.get("/{assessment_id}/submissions", response_model=List[AssessmentSubmission])
async def get_assessment_submissions(
    assessment_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get user's submissions for a specific assessment"""
    service = AssessmentService(db)
    
    # Get all user submissions and filter by assessment
    all_submissions = await service.get_user_submissions(
        current_user.id, skip=0, limit=1000
    )
    
    filtered_submissions = [
        sub for sub in all_submissions 
        if sub.assessment_id == assessment_id
    ][skip:skip + limit]
    
    return filtered_submissions

@router.get("/{assessment_id}/analytics")
async def get_assessment_analytics(
    assessment_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get assessment analytics (admin only)"""
    # Check if user is admin
    if current_user.role.value not in [UserRoleEnum.ADMIN.value]:

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    
    service = AssessmentService(db)
    return await service.get_assessment_analytics(assessment_id)

@router.post("/", response_model=Assessment, status_code=status.HTTP_201_CREATED)
async def create_assessment(
    assessment_data: AssessmentCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new assessment (admin only)"""
    # Check admin permissions
    print(f"role:{current_user.role.value}")
    if current_user.role.value not in [UserRoleEnum.ADMIN.value]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can create assessments"
        )
    
    service = AssessmentService(db)
    return await service.create_assessment(assessment_data)