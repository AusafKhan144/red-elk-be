import logging
import uuid
from functools import lru_cache
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from supabase import create_client, Client

from app.core.config import settings
from app.core.database import get_db
from app.models.models import User, TierEnum

logger = logging.getLogger("redelk.auth")

_bearer = HTTPBearer()


@lru_cache(maxsize=1)
def _get_supabase() -> Client:
    if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_ROLE_KEY:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set")
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    token = credentials.credentials
    try:
        response = _get_supabase().auth.get_user(token)
        sb_user = response.user if response is not None else None
        if not sb_user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    except HTTPException:
        raise
    except RuntimeError:
        raise
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    user_id = uuid.UUID(str(sb_user.id))
    user = await db.get(User, user_id)
    if not user:
        try:
            user = User(
                id=user_id,
                email=sb_user.email,
                tier=TierEnum.free,
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)
            logger.info("new user signed up: %s (id=%s)", user.email, user.id)
        except IntegrityError:
            # Another concurrent request already inserted this user; roll back
            # our failed transaction and fetch the row that won the race.
            await db.rollback()
            user = await db.get(User, user_id)
            if not user:
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create user")

    # Tag the request so the access-log middleware can attribute it to a user.
    request.state.user = user
    return user


async def get_current_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current_user
