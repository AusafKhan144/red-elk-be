"""Unit tests for get_current_user in app/dependencies.py."""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.exc import IntegrityError

from app.dependencies import get_current_user
from app.models.models import TierEnum, User


def _make_credentials(token: str = "tok") -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def _make_sb_user(uid: uuid.UUID, email: str = "user@example.com") -> MagicMock:
    sb_user = MagicMock()
    sb_user.id = str(uid)
    sb_user.email = email
    return sb_user


def _make_sb_response(sb_user) -> MagicMock:
    resp = MagicMock()
    resp.user = sb_user
    return resp


def _make_db(get_return=None) -> AsyncMock:
    db = AsyncMock()
    db.get = AsyncMock(return_value=get_return)
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    db.refresh = AsyncMock()
    return db


USER_ID = uuid.uuid4()


# ── happy paths ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_existing_user_returned():
    """Supabase token valid, user already in DB → returned as-is."""
    existing = User(id=USER_ID, email="user@example.com", tier=TierEnum.free)
    db = _make_db(get_return=existing)
    sb_user = _make_sb_user(USER_ID)

    with patch("app.dependencies._get_supabase") as mock_sb:
        mock_sb.return_value.auth.get_user.return_value = _make_sb_response(sb_user)
        result = await get_current_user(_make_credentials(), db)

    assert result is existing
    db.add.assert_not_called()
    db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_new_user_created():
    """User not in DB → row inserted, refreshed, and returned."""
    db = _make_db(get_return=None)
    sb_user = _make_sb_user(USER_ID)

    async def fake_refresh(obj):
        obj.id = USER_ID

    db.refresh = AsyncMock(side_effect=fake_refresh)

    with patch("app.dependencies._get_supabase") as mock_sb:
        mock_sb.return_value.auth.get_user.return_value = _make_sb_response(sb_user)
        result = await get_current_user(_make_credentials(), db)

    db.add.assert_called_once()
    db.commit.assert_called_once()
    db.refresh.assert_called_once()
    assert isinstance(result, User)
    assert result.tier == TierEnum.free


# ── race condition ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_race_condition_integrity_error():
    """INSERT raises IntegrityError (concurrent request won) → rollback + re-fetch."""
    existing = User(id=USER_ID, email="user@example.com", tier=TierEnum.free)

    db = _make_db(get_return=None)
    db.commit = AsyncMock(side_effect=IntegrityError("", {}, Exception()))
    # Second db.get (after rollback) returns the row that won the race
    db.get = AsyncMock(side_effect=[None, existing])

    sb_user = _make_sb_user(USER_ID)

    with patch("app.dependencies._get_supabase") as mock_sb:
        mock_sb.return_value.auth.get_user.return_value = _make_sb_response(sb_user)
        result = await get_current_user(_make_credentials(), db)

    db.rollback.assert_called_once()
    assert result is existing


@pytest.mark.asyncio
async def test_race_condition_row_vanishes_raises_500():
    """INSERT raises IntegrityError but re-fetch also returns None → 500."""
    db = _make_db(get_return=None)
    db.commit = AsyncMock(side_effect=IntegrityError("", {}, Exception()))
    db.get = AsyncMock(return_value=None)

    sb_user = _make_sb_user(USER_ID)

    with patch("app.dependencies._get_supabase") as mock_sb:
        mock_sb.return_value.auth.get_user.return_value = _make_sb_response(sb_user)
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(_make_credentials(), db)

    assert exc_info.value.status_code == 500


# ── auth failures ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_none_response_raises_401():
    """auth.get_user returns None → 401."""
    db = _make_db()
    with patch("app.dependencies._get_supabase") as mock_sb:
        mock_sb.return_value.auth.get_user.return_value = None
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(_make_credentials(), db)

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_response_user_none_raises_401():
    """auth.get_user returns a response but .user is None → 401."""
    db = _make_db()
    resp = MagicMock()
    resp.user = None
    with patch("app.dependencies._get_supabase") as mock_sb:
        mock_sb.return_value.auth.get_user.return_value = resp
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(_make_credentials(), db)

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_supabase_exception_raises_401():
    """Supabase client throws (e.g. network error, invalid token) → 401."""
    db = _make_db()
    with patch("app.dependencies._get_supabase") as mock_sb:
        mock_sb.return_value.auth.get_user.side_effect = Exception("network error")
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(_make_credentials(), db)

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_missing_config_raises_runtime_error():
    """RuntimeError from missing SUPABASE_URL/KEY is re-raised, not swallowed."""
    db = _make_db()
    with patch("app.dependencies._get_supabase", side_effect=RuntimeError("missing config")):
        with pytest.raises(RuntimeError, match="missing config"):
            await get_current_user(_make_credentials(), db)
