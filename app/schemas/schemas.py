import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, EmailStr

from app.models.models import SessionStatus, TierEnum


# ---------------------------------------------------------------------------
# Shared
# ---------------------------------------------------------------------------

class RadarPoint(BaseModel):
    dimension: str
    score: float
    label: str


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------

class MaturitySummary(BaseModel):
    overall_score: float
    tier_result: str
    radar_data: list[RadarPoint]
    as_of_session_id: uuid.UUID
    as_of_date: datetime


class UserProfile(BaseModel):
    id: uuid.UUID
    email: EmailStr
    tier: TierEnum
    company: Optional[str]
    role: str
    created_at: datetime
    maturity_summary: Optional[MaturitySummary] = None

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
    assessment_name: Optional[str] = None
    assessment_slug: Optional[str] = None
    score: Optional[float] = None                       # overall_score from linked report
    tier_result: Optional[str] = None                   # from linked report
    dimension_scores: Optional[list[RadarPoint]] = None # completed sessions only
    progress_pct: Optional[int] = None                  # in_progress sessions only

    model_config = {"from_attributes": True}


class AnswerIn(BaseModel):
    question_id: str
    dimension_id: str
    answer_value: float


class AnswerOut(BaseModel):
    question_id: str
    dimension_id: str
    answer_value: float

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------

class ReportOut(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    scores: dict[str, float]
    overall_score: float
    tier_result: str
    recommendations: dict[str, str]
    radar_data: list[RadarPoint]
    previous_radar_data: Optional[list[RadarPoint]] = None
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


class UserTierUpdate(BaseModel):
    tier: TierEnum


class AssessmentImportOut(BaseModel):
    id: uuid.UUID
    slug: str
    name: str
    version: int
    is_published: bool

    model_config = {"from_attributes": True}
