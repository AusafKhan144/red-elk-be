from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.api.endpoints import auth, assessments, users

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="AI Assessment Platform API - Comprehensive maturity and readiness assessments",
    version=settings.VERSION,
    docs_url="/hidden-docs",
    redoc_url="/hidden-redoc"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(assessments.router, prefix="/api/assessments", tags=["Assessments"])
# app.include_router(users.router, prefix="/api/users", tags=["Users"])

@app.get("/")
async def root():
    return {
        "message": "AI Assessment Platform API",
        "version": settings.VERSION,
        "docs": "/docs"
    }

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT
    }