# Import all models here to ensure they're registered with SQLAlchemy
from .user import User, UserTierEnum, UserRoleEnum
from .assessment import (
    Assessment, 
    Dimension, 
    Question, 
    AssessmentSubmission,
    TierEnum,
    QuestionTypeEnum
)

__all__ = [
    "User",
    "UserTierEnum", 
    "UserRoleEnum",
    "Assessment",
    "Dimension",
    "Question", 
    "AssessmentSubmission",
    "TierEnum",
    "QuestionTypeEnum"
]