from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.orm import declarative_base
from collections.abc import AsyncGenerator
from app.core.config import settings

DATABASE_URL = settings.database_url    

engine: AsyncEngine = create_async_engine(
    DATABASE_URL,
    echo=True,
    future=True,
    pool_pre_ping=True
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    autoflush=False,
)

Base = declarative_base()

# Dependency for FastAPI
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    session: AsyncSession = AsyncSessionLocal() 
    try:
        async with session:
            yield session
    finally:
        await session.close()


