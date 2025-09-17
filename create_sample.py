import asyncio
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.database import async_session_maker
from app.models.assessment import Assessment, Dimension, Question, TierEnum, QuestionTypeEnum
from app.models.user import User, UserTierEnum, UserRoleEnum
from app.core.security import get_password_hash

async def create_ai_transformation_assessment():
    async with async_session_maker() as session:
        
        # Create the AI Change Management Assessment
        assessment = Assessment(
            name="AI Change Management and Transformation Assessment",
            description="Comprehensive assessment of organizational readiness for AI transformation",
            category="AI Transformation",
            is_active=True
        )
        session.add(assessment)
        await session.flush()

        # 1. AI Adoption Communication Dimension
        comm_dimension = Dimension(
            assessment_id=assessment.id,
            name="AI Adoption Communication",
            description="Communication strategies and effectiveness for AI adoption",
            weight=1.0,
            order_index=1
        )
        session.add(comm_dimension)
        await session.flush()

        # Employee Understanding Question
        q1 = Question(
            dimension_id=comm_dimension.id,
            text="How well do employees understand the purpose and goals of AI-driven changes in the organization?",
            question_type=QuestionTypeEnum.SCALE,
            options={
                "min_value": 1,
                "max_value": 5,
                "labels": [
                    "No understanding of AI transformation goals",
                    "Minimal understanding of AI adoption goals", 
                    "Moderate understanding of AI adoption goals",
                    "Strong understanding of AI adoption goals",
                    "Comprehensive understanding and alignment with AI transformation objectives"
                ]
            },
            required_tier=TierEnum.FREE,
            scoring_weight=1.0,
            order_index=1
        )
        session.add(q1)

        # Stakeholder Engagement Question  
        q2 = Question(
            dimension_id=comm_dimension.id,
            text="How effectively does your organization engage external and internal stakeholders in AI adoption?",
            question_type=QuestionTypeEnum.SCALE,
            options={
                "min_value": 1,
                "max_value": 5,
                "labels": [
                    "No engagement with stakeholders",
                    "Minimal engagement with AI stakeholders",
                    "Moderate engagement with AI stakeholders", 
                    "Strong engagement with AI stakeholders",
                    "Comprehensive engagement and communication with all stakeholders"
                ]
            },
            required_tier=TierEnum.PREMIUM,
            scoring_weight=1.0,
            order_index=2
        )
        session.add(q2)

        # Communication Across Departments Question
        q3 = Question(
            dimension_id=comm_dimension.id,
            text="How well does your organization communicate AI adoption efforts across different departments?",
            question_type=QuestionTypeEnum.SCALE,
            options={
                "min_value": 1,
                "max_value": 5,
                "labels": [
                    "No communication across departments",
                    "Minimal communication across departments",
                    "Moderate communication across departments",
                    "Strong communication across departments", 
                    "Comprehensive cross-functional communication on AI transformation"
                ]
            },
            required_tier=TierEnum.PREMIUM,
            scoring_weight=1.0,
            order_index=3
        )
        session.add(q3)

        # AI Communication Tools Question
        q4 = Question(
            dimension_id=comm_dimension.id,
            text="How well-equipped is your organization with tools for communicating AI-related progress?",
            question_type=QuestionTypeEnum.SCALE,
            options={
                "min_value": 1,
                "max_value": 5,
                "labels": [
                    "No tools for AI communication",
                    "Minimal AI communication tools",
                    "Moderate AI communication tools",
                    "Strong AI communication tools",
                    "Comprehensive tools for communicating AI"
                ]
            },
            required_tier=TierEnum.BASIC,
            scoring_weight=1.0,
            order_index=4
        )
        session.add(q4)

        # 2. Employee Engagement and Training Dimension
        engagement_dimension = Dimension(
            assessment_id=assessment.id,
            name="Employee Engagement and Training",
            description="Employee involvement and preparation for AI transformation",
            weight=1.2,
            order_index=2
        )
        session.add(engagement_dimension)
        await session.flush()

        # Employee AI Engagement Question
        q5 = Question(
            dimension_id=engagement_dimension.id,
            text="How well does your organization engage employees in AI transformation projects?",
            question_type=QuestionTypeEnum.SCALE,
            options={
                "min_value": 1,
                "max_value": 5,
                "labels": [
                    "No employee engagement in AI projects",
                    "Minimal employee engagement in AI projects",
                    "Moderate employee engagement",
                    "Strong employee engagement", 
                    "Comprehensive employee engagement in AI projects"
                ]
            },
            required_tier=TierEnum.PREMIUM,
            scoring_weight=1.0,
            order_index=1
        )
        session.add(q5)

        # 3. Change Management Strategy Dimension
        strategy_dimension = Dimension(
            assessment_id=assessment.id,
            name="Change Management Strategy", 
            description="Strategic approach to managing AI-driven organizational change",
            weight=1.5,
            order_index=3
        )
        session.add(strategy_dimension)
        await session.flush()

        # AI Change Readiness Question
        q6 = Question(
            dimension_id=strategy_dimension.id,
            text="How well-prepared is your organization for the changes brought by AI transformation?",
            question_type=QuestionTypeEnum.SCALE,
            options={
                "min_value": 1,
                "max_value": 5,
                "labels": [
                    "No preparation for AI change",
                    "Minimal preparation for AI-driven change",
                    "Moderate preparation for AI-driven change",
                    "Strong preparation for AI-driven change",
                    "Comprehensive readiness for AI transformation across the organization"
                ]
            },
            required_tier=TierEnum.FREE,
            scoring_weight=1.0,
            order_index=1
        )
        session.add(q6)

        # AI Change Management Planning Question
        q7 = Question(
            dimension_id=strategy_dimension.id,
            text="How well-defined is your organization's change management planning for AI initiatives?",
            question_type=QuestionTypeEnum.SCALE,
            options={
                "min_value": 1,
                "max_value": 5,
                "labels": [
                    "No formal change management planning",
                    "Basic change management planning",
                    "Structured change management planning", 
                    "Comprehensive change management planning",
                    "Advanced, integrated change management planning"
                ]
            },
            required_tier=TierEnum.BASIC,
            scoring_weight=1.0,
            order_index=2
        )
        session.add(q7)

        await session.commit()
        print("✅ AI Change Management Assessment created successfully!")
        print(f"📊 Assessment ID: {assessment.id}")
        print(f"📋 Total Dimensions: 3")
        print(f"❓ Total Questions: 7")
        print(f"🆓 Free Questions: 2")
        print(f"💼 Basic Questions: 2") 
        print(f"⭐ Premium Questions: 3")

if __name__ == "__main__":
    asyncio.run(create_ai_transformation_assessment())