from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime
from app.models.assessment import TierEnum, QuestionTypeEnum

class QuestionBase(BaseModel):
    text: str
    question_type: QuestionTypeEnum
    options: Optional[Dict[str, Any]] = None
    required_tier: TierEnum
    scoring_weight: float = 1.0
    order_index: int

class Question(QuestionBase):
    id: int
    dimension_id: int
    
    class Config:
        from_attributes = True

class DimensionBase(BaseModel):
    name: str
    description: Optional[str] = None
    weight: float = 1.0
    order_index: int

class Dimension(DimensionBase):
    id: int
    assessment_id: int
    questions: List[Question] = []
    
    class Config:
        from_attributes = True

class AssessmentBase(BaseModel):
    name: str
    description: Optional[str] = None
    category: str

class Assessment(AssessmentBase):
    id: int
    is_active: bool
    created_at: datetime
    dimensions: List[Dimension] = []
    
    class Config:
        from_attributes = True

class AssessmentSubmissionCreate(BaseModel):
    assessment_id: int
    company_name: Optional[str] = None
    responses: Dict[str, Any]
    tier_used: TierEnum

class AssessmentSubmission(BaseModel):
    id: int
    assessment_id: int
    user_id: int
    company_name: Optional[str] = None
    responses: Dict[str, Any]
    scores: Optional[Dict[str, Any]] = None
    tier_used: TierEnum
    is_completed: bool
    started_at: datetime
    completed_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True

class QuestionCreate(QuestionBase):
    pass

class DimensionCreate(DimensionBase):
    questions: List[QuestionCreate] = []

class AssessmentCreate(AssessmentBase):
    dimensions: List[DimensionCreate] = []