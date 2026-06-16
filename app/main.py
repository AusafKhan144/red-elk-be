import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logging import request_id_var, setup_logging
from app.routers import auth, assessments, sessions, reports, admin

setup_logging("DEBUG" if settings.ENVIRONMENT == "development" else "INFO")
logger = logging.getLogger("redelk.access")

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Red Elk AI Maturity Assessment API",
    version=settings.VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
)


@app.middleware("http")
async def access_log(request: Request, call_next):
    """Log one structured line per request, tagged with the calling user.

    `request.state.user` is populated by `get_current_user` while the route's
    dependencies resolve, so by the time the response is ready we know who made
    the call (or "anon" for unauthenticated/failed-auth requests).
    """
    request_id = uuid.uuid4().hex[:8]
    token = request_id_var.set(request_id)
    start = time.perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        duration_ms = (time.perf_counter() - start) * 1000
        user = getattr(request.state, "user", None)
        actor = f"{user.email}<{user.tier.value}>" if user is not None else "anon"
        # Health/root checks are noise — drop them to DEBUG.
        level = logging.DEBUG if request.url.path in ("/health", "/") else logging.INFO
        logger.log(
            level,
            "%s %s -> %d in %.0fms user=%s",
            request.method,
            request.url.path,
            status_code,
            duration_ms,
            actor,
        )
        request_id_var.reset(token)

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
