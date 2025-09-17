from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from app.core.database import get_db
from app.services.assessment_service import AssessmentService
from app.schemas.user import User
from app.schemas.assessment import AssessmentSubmission
from app.api.deps import get_current_user
from app.models.user import User as UserModel

router = APIRouter()

@router.get("/me/submissions", response_model=List[AssessmentSubmission])
async def get_my_submissions(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get current user's assessment submissions"""
    service = AssessmentService(db)
    return await service.get_user_submissions(
        current_user.id, skip=skip, limit=limit
    )

@router.get("/me/submissions/{submission_id}", response_model=AssessmentSubmission)
async def get_my_submission(
    submission_id: int,
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get specific submission by ID"""
    service = AssessmentService(db)
    submission = await service.get_submission_by_id(submission_id, current_user.id)
    
    if not submission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Submission not found"
        )
    
    return submission

@router.get("/me/dashboard")
async def get_user_dashboard(
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get user dashboard data"""
    service = AssessmentService(db)
    
    # Get recent submissions
    recent_submissions = await service.get_user_submissions(
        current_user.id, skip=0, limit=5
    )
    
    # Calculate stats
    total_submissions = len(await service.get_user_submissions(
        current_user.id, skip=0, limit=1000
    ))
    
    completed_submissions = [
        sub for sub in recent_submissions if sub.is_completed
    ]
    
    return {
        "user": current_user,
        "stats": {
            "total_assessments": total_submissions,
            "completed_assessments": len(completed_submissions),
            "tier": current_user.tier.value
        },
        "recent_submissions": recent_submissions[:3],
        "available_tiers": ["FREE", "BASIC", "PREMIUM"]
    }