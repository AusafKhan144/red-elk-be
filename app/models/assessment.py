from datetime import datetime
from sqlalchemy import Integer, String, Text, JSON, DateTime, ForeignKey, Enum, Float, Boolean
from sqlalchemy.orm import relationship, mapped_column, Mapped
from sqlalchemy.sql import func
from app.core.database import Base
from typing import Optional, List, Dict, Any
import enum

class TierEnum(enum.Enum):
    FREE = "free"
    BASIC = "basic"
    PREMIUM = "premium"

class QuestionTypeEnum(enum.Enum):
    MULTIPLE_CHOICE = "multiple_choice"
    SCALE = "scale"
    BOOLEAN = "boolean"
    TEXT = "text"

class Assessment(Base):
    __tablename__ = "assessments"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String, unique=True, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    dimensions: Mapped[List["Dimension"]] = relationship("Dimension", back_populates="assessment", lazy="selectin")
    submissions: Mapped[List["AssessmentSubmission"]] = relationship("AssessmentSubmission", back_populates="assessment")

class Dimension(Base):
    __tablename__ = "dimensions"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    assessment_id: Mapped[int] = mapped_column(Integer, ForeignKey("assessments.id"))
    name: Mapped[str] = mapped_column(String)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    order_index: Mapped[int] = mapped_column(Integer)
    
    # Relationships
    assessment: Mapped["Assessment"] = relationship("Assessment", back_populates="dimensions")
    questions: Mapped[List["Question"]] = relationship("Question", back_populates="dimension", lazy="selectin")

class Question(Base):
    __tablename__ = "questions"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    dimension_id: Mapped[int] = mapped_column(Integer, ForeignKey("dimensions.id"))
    text: Mapped[str] = mapped_column(Text)
    question_type: Mapped[QuestionTypeEnum] = mapped_column(Enum(QuestionTypeEnum))
    options: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    required_tier: Mapped[TierEnum] = mapped_column(Enum(TierEnum))
    scoring_weight: Mapped[float] = mapped_column(Float, default=1.0)
    order_index: Mapped[int] = mapped_column(Integer)
    
    # Relationships
    dimension: Mapped["Dimension"] = relationship("Dimension", back_populates="questions")

class AssessmentSubmission(Base):
    
    __tablename__ = "assessment_submissions"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    assessment_id: Mapped[int] = mapped_column(Integer, ForeignKey("assessments.id"))
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"))
    company_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    responses: Mapped[Dict[str, Any]] = mapped_column(JSON)
    scores: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    tier_used: Mapped[TierEnum] = mapped_column(Enum(TierEnum))
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    assessment: Mapped["Assessment"] = relationship("Assessment", back_populates="submissions")
    user: Mapped["User"] = relationship("User") # type: ignore 