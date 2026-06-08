"""Redesign to brief schema: 5 tables with Supabase auth and JSONB config

Revision ID: a1b2c3d4e5f6
Revises: 5658704f7c4c
Create Date: 2026-06-08 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '5658704f7c4c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop old tables (order respects FK constraints)
    op.drop_table('assessment_submissions')
    op.drop_table('questions')
    op.drop_table('dimensions')
    op.drop_table('assessments')
    op.drop_table('users')

    # Drop old enums
    op.execute("DROP TYPE IF EXISTS tierenum")
    op.execute("DROP TYPE IF EXISTS questiontypeenum")
    op.execute("DROP TYPE IF EXISTS userroleenum")
    op.execute("DROP TYPE IF EXISTS usertierenum")

    # Create new enums
    tier_enum = postgresql.ENUM('free', 'basic', 'premium', name='tier_enum', create_type=False)
    tier_enum.create(op.get_bind(), checkfirst=True)

    session_status_enum = postgresql.ENUM(
        'in_progress', 'completed', 'abandoned',
        name='session_status_enum', create_type=False
    )
    session_status_enum.create(op.get_bind(), checkfirst=True)

    _tier = postgresql.ENUM('free', 'basic', 'premium', name='tier_enum', create_type=False)
    _status = postgresql.ENUM('in_progress', 'completed', 'abandoned', name='session_status_enum', create_type=False)

    # users — id is UUID from Supabase, no hashed_password
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('email', sa.String(), nullable=False, unique=True),
        sa.Column('tier', _tier, nullable=False, server_default='free'),
        sa.Column('company', sa.String(), nullable=True),
        sa.Column('role', sa.String(), nullable=False, server_default='user'),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
    )

    # assessments — all config (dimensions, questions, scoring) stored as JSONB
    op.create_table(
        'assessments',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('slug', sa.String(), nullable=False, unique=True),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('config', postgresql.JSONB(), nullable=False),
        sa.Column('is_published', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
    )

    # assessment_sessions
    op.create_table(
        'assessment_sessions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('assessment_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('assessments.id', ondelete='CASCADE'), nullable=False),
        sa.Column('status', _status, nullable=False, server_default='in_progress'),
        sa.Column('tier_at_time', _tier, nullable=False),
        sa.Column('started_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('completed_at', sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index('ix_assessment_sessions_user_id', 'assessment_sessions', ['user_id'])
    op.create_index('ix_assessment_sessions_assessment_id', 'assessment_sessions', ['assessment_id'])

    # responses — one row per answer
    op.create_table(
        'responses',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('session_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('assessment_sessions.id', ondelete='CASCADE'), nullable=False),
        sa.Column('question_id', sa.String(), nullable=False),
        sa.Column('dimension_id', sa.String(), nullable=False),
        sa.Column('answer_value', sa.Numeric(), nullable=False),
        sa.Column('answered_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_responses_session_id', 'responses', ['session_id'])
    # Unique constraint: one answer per question per session
    op.create_unique_constraint('uq_responses_session_question', 'responses', ['session_id', 'question_id'])

    # reports — unique per session
    op.create_table(
        'reports',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('session_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('assessment_sessions.id', ondelete='CASCADE'), nullable=False, unique=True),
        sa.Column('scores', postgresql.JSONB(), nullable=False),
        sa.Column('overall_score', sa.Numeric(), nullable=False),
        sa.Column('tier_result', sa.String(), nullable=False),
        sa.Column('pdf_url', sa.String(), nullable=True),
        sa.Column('generated_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
    )


def downgrade() -> None:
    op.drop_table('reports')
    op.drop_table('responses')
    op.drop_table('assessment_sessions')
    op.drop_table('assessments')
    op.drop_table('users')
    op.execute("DROP TYPE IF EXISTS session_status_enum")
    op.execute("DROP TYPE IF EXISTS tier_enum")
