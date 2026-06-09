from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies import get_current_user
from app.models.models import User
from app.schemas.schemas import UserProfile, UserUpdate

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserProfile)
async def register(
    body: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Sync local user profile after Supabase registration.
    The JWT must already be valid (get_current_user auto-creates the row on first call).
    This endpoint lets the user supply additional fields (company).
    """
    if body.company is not None:
        current_user.company = body.company
        await db.commit()
        await db.refresh(current_user)
    return UserProfile.model_validate(current_user)


@router.get("/me", response_model=UserProfile)
async def me(current_user: User = Depends(get_current_user)):
    return UserProfile.model_validate(current_user)


@router.patch("/me", response_model=UserProfile)
async def update_me(
    body: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if body.company is not None:
        current_user.company = body.company
        await db.commit()
        await db.refresh(current_user)
    return UserProfile.model_validate(current_user)
