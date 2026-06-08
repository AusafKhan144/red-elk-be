import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean, Enum, ForeignKey, Numeric, String, Text, Integer,
    TIMESTAMP, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass


class TierEnum(str, enum.Enum):
    free = "free"
    basic = "basic"
    premium = "premium"


class SessionStatus(str, enum.Enum):
    in_progress = "in_progress"
    completed = "completed"
    abandoned = "abandoned"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    tier: Mapped[TierEnum] = mapped_column(
        Enum(TierEnum, name="tier_enum"), nullable=False, default=TierEnum.free
    )
    company: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    role: Mapped[str] = mapped_column(String, nullable=False, default="user")
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    sessions: Mapped[list["AssessmentSession"]] = relationship(back_populates="user")


class Assessment(Base):
    __tablename__ = "assessments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    slug: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False)
    is_published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    sessions: Mapped[list["AssessmentSession"]] = relationship(back_populates="assessment")


class AssessmentSession(Base):
    __tablename__ = "assessment_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    assessment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[SessionStatus] = mapped_column(
        Enum(SessionStatus, name="session_status_enum"),
        nullable=False,
        default=SessionStatus.in_progress,
    )
    tier_at_time: Mapped[TierEnum] = mapped_column(
        Enum(TierEnum, name="tier_enum"), nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )

    user: Mapped["User"] = relationship(back_populates="sessions")
    assessment: Mapped["Assessment"] = relationship(back_populates="sessions")
    responses: Mapped[list["Response"]] = relationship(back_populates="session")
    report: Mapped[Optional["Report"]] = relationship(back_populates="session", uselist=False)


class Response(Base):
    __tablename__ = "responses"
    __table_args__ = (
        UniqueConstraint("session_id", "question_id", name="uq_responses_session_question"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assessment_sessions.id", ondelete="CASCADE"), nullable=False
    )
    question_id: Mapped[str] = mapped_column(String, nullable=False)
    dimension_id: Mapped[str] = mapped_column(String, nullable=False)
    answer_value: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    answered_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    session: Mapped["AssessmentSession"] = relationship(back_populates="responses")


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assessment_sessions.id", ondelete="CASCADE"),
        nullable=False, unique=True
    )
    scores: Mapped[dict] = mapped_column(JSONB, nullable=False)
    overall_score: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    tier_result: Mapped[str] = mapped_column(String, nullable=False)
    pdf_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    generated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    session: Mapped["AssessmentSession"] = relationship(back_populates="report")
