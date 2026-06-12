"""
Shared fixtures: in-memory SQLite async DB, FastAPI test client with auth/db
overrides, and a sample assessment config.

The models use PostgreSQL-specific column types (JSONB, UUID); the @compiles
hooks below map them to SQLite-compatible DDL so the schema can be created
in-memory for tests.
"""
import uuid
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.pool import StaticPool

from app.models.models import Assessment, Base, TierEnum, User


@compiles(JSONB, "sqlite")
def _jsonb_sqlite(type_, compiler, **kw):
    return "JSON"


@compiles(PG_UUID, "sqlite")
def _uuid_sqlite(type_, compiler, **kw):
    return "CHAR(32)"


def make_config() -> dict:
    """Two-dimension assessment: per dimension 2 free / 2 basic / 1 premium questions."""
    def questions(prefix: str) -> list[dict]:
        tiers = ["free", "free", "basic", "basic", "premium"]
        return [
            {"id": f"{prefix}{i + 1}", "text": f"Question {prefix}{i + 1}",
             "tier": tier, "type": "scale", "max_score": 5}
            for i, tier in enumerate(tiers)
        ]

    levels = ["nascent", "developing", "maturing", "leading"]
    return {
        "slug": "test-assessment",
        "name": "Test Assessment",
        "version": 1,
        "is_published": True,
        "dimensions": [
            {"id": "strategy", "name": "Strategy & Vision", "weight": 0.6,
             "questions": questions("s")},
            {"id": "data", "name": "Data & Infrastructure", "weight": 0.4,
             "questions": questions("d")},
        ],
        "scoring": {
            "thresholds": {
                "nascent": [0, 30], "developing": [30, 55],
                "maturing": [55, 75], "leading": [75, 100],
            },
            "recommendations": {
                "strategy": {lvl: f"strategy-{lvl}" for lvl in levels},
                "data": {lvl: f"data-{lvl}" for lvl in levels},
            },
        },
    }


@pytest.fixture
def config() -> dict:
    return make_config()


@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_maker(engine):
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def db(session_maker):
    async with session_maker() as session:
        yield session


@pytest_asyncio.fixture
async def user(db) -> User:
    u = User(id=uuid.uuid4(), email="test@example.com", tier=TierEnum.free, role="user")
    db.add(u)
    await db.commit()
    return u


@pytest_asyncio.fixture
async def assessment(db, config) -> Assessment:
    a = Assessment(
        id=uuid.uuid4(),
        slug="test-assessment",
        name="Test Assessment",
        description="desc",
        config=config,
        is_published=True,
        version=1,
    )
    db.add(a)
    await db.commit()
    return a


@pytest.fixture
def mock_pdf(monkeypatch) -> AsyncMock:
    """Replace the real WeasyPrint/Cloudinary pipeline with a stub URL."""
    mock = AsyncMock(return_value="https://res.cloudinary.test/report.pdf")
    monkeypatch.setattr("app.services.pdf.generate_and_upload_pdf", mock)
    return mock


@pytest_asyncio.fixture
async def client(db, user, session_maker, monkeypatch, mock_pdf):
    from app.core.database import get_db
    from app.dependencies import get_current_user
    from app.main import app
    import app.routers.sessions as sessions_router

    # Background PDF task must use the test DB, not the real engine
    monkeypatch.setattr(sessions_router, "async_session_maker", session_maker)

    async def _override_get_db():
        yield db

    async def _override_user():
        return user

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = _override_user
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c
    finally:
        app.dependency_overrides.clear()
