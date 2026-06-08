import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, EmailStr

from app.models.models import SessionStatus, TierEnum


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------

class UserProfile(BaseModel):
    id: uuid.UUID
    email: EmailStr
    tier: TierEnum
    company: Optional[str]
    role: str
    created_at: datetime

    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    company: Optional[str] = None


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class RegisterIn(BaseModel):
    company: Optional[str] = None


# ---------------------------------------------------------------------------
# Assessments
# ---------------------------------------------------------------------------

class AssessmentListItem(BaseModel):
    id: uuid.UUID
    slug: str
    name: str
    description: Optional[str]
    version: int

    model_config = {"from_attributes": True}


class QuestionOut(BaseModel):
    id: str
    text: str
    tier: str
    type: str
    options: Optional[Any] = None
    max_score: float


class DimensionOut(BaseModel):
    id: str
    name: str
    weight: float
    questions: list[QuestionOut]


class AssessmentOut(BaseModel):
    id: uuid.UUID
    slug: str
    name: str
    description: Optional[str]
    version: int
    dimensions: list[DimensionOut]

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------

class SessionStartIn(BaseModel):
    assessment_slug: str


class SessionOut(BaseModel):
    id: uuid.UUID
    assessment_id: uuid.UUID
    status: SessionStatus
    tier_at_time: TierEnum
    started_at: datetime
    completed_at: Optional[datetime]

    model_config = {"from_attributes": True}


class AnswerIn(BaseModel):
    question_id: str
    dimension_id: str
    answer_value: float


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------

class RadarPoint(BaseModel):
    dimension: str
    score: float
    label: str


class ReportOut(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    scores: dict[str, float]
    overall_score: float
    tier_result: str
    recommendations: dict[str, str]
    radar_data: list[RadarPoint]
    pdf_url: Optional[str]
    generated_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------

class AdminSessionOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    assessment_id: uuid.UUID
    status: SessionStatus
    tier_at_time: TierEnum
    started_at: datetime
    completed_at: Optional[datetime]

    model_config = {"from_attributes": True}


class DimensionAnalytics(BaseModel):
    dimension_id: str
    dimension_name: str
    avg_score: float


class AnalyticsOut(BaseModel):
    total_sessions: int
    completed_sessions: int
    sessions_by_tier: dict[str, int]
    avg_overall_score: Optional[float]
    dimensions: list[DimensionAnalytics]


class UserRoleUpdate(BaseModel):
    role: str


class AssessmentImportOut(BaseModel):
    id: uuid.UUID
    slug: str
    name: str
    version: int
    is_published: bool

    model_config = {"from_attributes": True}
