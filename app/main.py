from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.routers import auth, assessments, sessions, reports, admin

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Red Elk AI Maturity Assessment API",
    version=settings.VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(assessments.router)
app.include_router(sessions.router)
app.include_router(reports.router)
app.include_router(admin.router)



@app.get("/", include_in_schema=False)
async def root():
    return {"service": settings.PROJECT_NAME, "version": settings.VERSION}


@app.get("/health", include_in_schema=False)
async def health():
    return {"status": "ok", "version": settings.VERSION}
