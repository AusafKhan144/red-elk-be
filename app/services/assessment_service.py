from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from sqlalchemy.orm import selectinload
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from app.models.assessment import Assessment, Dimension, Question, AssessmentSubmission, TierEnum, QuestionTypeEnum
from app.schemas.assessment import AssessmentCreate, AssessmentSubmissionCreate
from fastapi import HTTPException, status

class AssessmentService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_all_assessments(self, skip: int = 0, limit: int = 100) -> List[Assessment]:
        """Get all active assessments"""
        result = await self.db.execute(
            select(Assessment)
            .options(selectinload(Assessment.dimensions).selectinload(Dimension.questions))
            .where(Assessment.is_active == True)
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_assessment_by_id(self, assessment_id: int) -> Optional[Assessment]:
        """Get assessment by ID with all relations"""
        result = await self.db.execute(
            select(Assessment)
            .options(selectinload(Assessment.dimensions).selectinload(Dimension.questions))
            .where(Assessment.id == assessment_id)
        )
        return result.scalar_one_or_none()

    async def get_assessment_for_user_tier(self, assessment_id: int, user_tier: TierEnum) -> Optional[Dict]:
        """Get assessment filtered by user tier"""
        assessment = await self.get_assessment_by_id(assessment_id)
        if not assessment or not assessment.is_active:
            return None

        # Define tier hierarchy
        tier_hierarchy = {
            TierEnum.FREE: [TierEnum.FREE],
            TierEnum.BASIC: [TierEnum.FREE, TierEnum.BASIC],
            TierEnum.PREMIUM: [TierEnum.FREE, TierEnum.BASIC, TierEnum.PREMIUM]
        }

        allowed_tiers = tier_hierarchy.get(user_tier, [TierEnum.FREE])
        
        # Filter assessment data
        filtered_assessment = {
            "id": assessment.id,
            "name": assessment.name,
            "description": assessment.description,
            "category": assessment.category,
            "dimensions": []
        }

        for dimension in sorted(assessment.dimensions, key=lambda d: d.order_index):
            # Filter questions by tier
            accessible_questions = [
                {
                    "id": q.id,
                    "text": q.text,
                    "question_type": q.question_type.value,
                    "options": q.options or {},
                    "required_tier": q.required_tier.value,
                    "scoring_weight": q.scoring_weight,
                    "order_index": q.order_index
                }
                for q in sorted(dimension.questions, key=lambda q: q.order_index)
                if q.required_tier in allowed_tiers
            ]
            
            if accessible_questions:
                filtered_assessment["dimensions"].append({
                    "id": dimension.id,
                    "name": dimension.name,
                    "description": dimension.description,
                    "weight": dimension.weight,
                    "order_index": dimension.order_index,
                    "questions": accessible_questions
                })

        return filtered_assessment

    async def submit_assessment_responses(self, submission_data: AssessmentSubmissionCreate, user_id: int) -> AssessmentSubmission:
        """Submit assessment responses and calculate scores"""
        # Verify assessment exists
        assessment = await self.get_assessment_by_id(submission_data.assessment_id)
        if not assessment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Assessment not found"
            )

        # Calculate scores
        scores = await self._calculate_assessment_scores(
            submission_data.assessment_id, 
            submission_data.responses,
            submission_data.tier_used
        )
        
        # Create submission record
        db_submission = AssessmentSubmission(
            assessment_id=submission_data.assessment_id,
            user_id=user_id,
            company_name=submission_data.company_name,
            responses=submission_data.responses,
            scores=scores,
            tier_used=submission_data.tier_used,
            is_completed=True,
            completed_at=datetime.now(timezone.utc)
        )
        
        self.db.add(db_submission)
        await self.db.commit()
        await self.db.refresh(db_submission)
        return db_submission

    async def _calculate_assessment_scores(self, assessment_id: int, responses: Dict[str, Any], tier_used: TierEnum) -> Dict[str, Any]:
        """Calculate assessment scores based on responses"""
        assessment = await self.get_assessment_by_id(assessment_id)
        if not assessment:
            return {}

        dimension_scores = {}
        total_weighted_score = 0
        total_weight = 0

        for dimension in assessment.dimensions:
            dimension_score = 0
            dimension_max_score = 0
            
            for question in dimension.questions:
                question_id = str(question.id)
                
                if question_id in responses:
                    response_value = responses[question_id]
                    question_score = self._calculate_question_score(question, response_value)
                    
                    dimension_score += question_score * question.scoring_weight
                    dimension_max_score += question.scoring_weight

            # Calculate dimension percentage
            dimension_percentage = (dimension_score / dimension_max_score * 100) if dimension_max_score > 0 else 0
            
            dimension_scores[dimension.name] = {
                "score": dimension_score,
                "max_score": dimension_max_score,
                "percentage": round(dimension_percentage, 2),
                "weight": dimension.weight
            }
            
            total_weighted_score += dimension_percentage * dimension.weight
            total_weight += dimension.weight

        # Calculate overall score
        overall_percentage = (total_weighted_score / total_weight) if total_weight > 0 else 0
        
        return {
            "overall_score": round(overall_percentage, 2),
            "dimension_scores": dimension_scores,
            "tier_used": tier_used.value,
            "calculated_at": datetime.now(timezone.utc).isoformat(),
            "total_questions_answered": len(responses)
        }

    def _calculate_question_score(self, question: Question, response_value: Any) -> float:
        """Calculate score for a single question"""
        if question.question_type == QuestionTypeEnum.SCALE:
            # Assume scale questions have a max value in options
            max_value = question.options.get('max_value', 5) if question.options else 5
            return float(response_value) / max_value if response_value else 0
        
        elif question.question_type == QuestionTypeEnum.BOOLEAN:
            return 1.0 if response_value else 0.0
        
        elif question.question_type == QuestionTypeEnum.MULTIPLE_CHOICE:
            # Check if options have scoring defined
            if question.options and 'scoring' in question.options:
                return question.options['scoring'].get(str(response_value), 0)
            return 0.5  # Default score for multiple choice
        
        elif question.question_type == QuestionTypeEnum.TEXT:
            # Text responses get a neutral score
            return 0.5 if response_value and str(response_value).strip() else 0
        
        return 0

    async def get_user_submissions(self, user_id: int, skip: int = 0, limit: int = 100) -> List[AssessmentSubmission]:
        """Get user's assessment submissions"""
        result = await self.db.execute(
            select(AssessmentSubmission)
            .options(selectinload(AssessmentSubmission.assessment))
            .where(AssessmentSubmission.user_id == user_id)
            .order_by(AssessmentSubmission.completed_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_submission_by_id(self, submission_id: int, user_id: int) -> Optional[AssessmentSubmission]:
        """Get specific submission by ID for a user"""
        result = await self.db.execute(
            select(AssessmentSubmission)
            .options(selectinload(AssessmentSubmission.assessment))
            .where(
                and_(
                    AssessmentSubmission.id == submission_id,
                    AssessmentSubmission.user_id == user_id
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_assessment_analytics(self, assessment_id: int) -> Dict[str, Any]:
        """Get analytics for an assessment (admin only)"""
        # Total submissions
        total_submissions = await self.db.execute(
            select(func.count(AssessmentSubmission.id))
            .where(AssessmentSubmission.assessment_id == assessment_id)
        )
        total_count = total_submissions.scalar()

        # Submissions by tier
        tier_breakdown = await self.db.execute(
            select(AssessmentSubmission.tier_used, func.count(AssessmentSubmission.id))
            .where(AssessmentSubmission.assessment_id == assessment_id)
            .group_by(AssessmentSubmission.tier_used)
        )
        
        tier_stats = {tier.value: count for tier, count in tier_breakdown.all()}

        return {
            "assessment_id": assessment_id,
            "total_submissions": total_count,
            "submissions_by_tier": tier_stats,
            "generated_at": datetime.now(timezone.utc).isoformat()
        }
    

    async def create_assessment(self, assessment_data: AssessmentCreate) -> Assessment:
        """Create a new assessment with dimensions and questions"""
        try:
            # Create assessment
            db_assessment = Assessment(
                name=assessment_data.name,
                description=assessment_data.description,
                category=assessment_data.category,
                is_active=True
            )
            
            self.db.add(db_assessment)
            await self.db.flush()  # Get the ID
            
            # Create dimensions and questions
            for dim_data in assessment_data.dimensions:
                db_dimension = Dimension(
                    assessment_id=db_assessment.id,
                    name=dim_data.name,
                    description=dim_data.description,
                    weight=dim_data.weight,
                    order_index=dim_data.order_index
                )
                self.db.add(db_dimension)
                await self.db.flush()
                
                # Create questions
                for question_data in dim_data.questions:
                    db_question = Question(
                        dimension_id=db_dimension.id,
                        text=question_data.text,
                        question_type=question_data.question_type,
                        options=question_data.options,
                        required_tier=question_data.required_tier,
                        scoring_weight=question_data.scoring_weight,
                        order_index=question_data.order_index
                    )
                    self.db.add(db_question)
            
            await self.db.commit()
            await self.db.refresh(db_assessment)
            
            # Return with relationships loaded
            return await self.get_assessment_by_id(db_assessment.id)
            
        except Exception as e:
            await self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to create assessment: {str(e)}"
            )