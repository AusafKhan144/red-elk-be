from fastapi import FastAPI
from app.api import auth, assessments

app = FastAPI(title="AI Assessment Platform", version="0.1")

# Routers
app.include_router(auth.router)
# app.include_router(assessments.router, prefix="/api/assessments", tags=["assessments"])

@app.get("/")
def health_check():
    return {"status": "ok"}
