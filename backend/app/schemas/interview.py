import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.session import SessionStatus


class SessionCreate(BaseModel):
    job_role: str
    resume_text: str | None = None
    jd_text: str | None = None


class SessionResponse(BaseModel):
    id: uuid.UUID
    job_role: str
    status: SessionStatus
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SkillResponse(BaseModel):
    id: uuid.UUID
    name: str
    category: str
    confidence_score: float
    years_experience: float | None
    is_bluff_risk: bool

    model_config = {"from_attributes": True}


class QuestionResponse(BaseModel):
    id: uuid.UUID
    text: str
    question_type: str
    difficulty: str
    order_index: int
    skill_id: uuid.UUID | None

    model_config = {"from_attributes": True}


class AnswerCreate(BaseModel):
    text: str


class AnswerResponse(BaseModel):
    id: uuid.UUID
    question_id: uuid.UUID
    text: str
    quality_score: float | None
    is_bluff_detected: bool
    follow_up_generated: bool

    model_config = {"from_attributes": True}


class SubmitAnswerResponse(BaseModel):
    """Returned when a candidate submits an answer.

    Includes the persisted answer, the LLM evaluation, and — if the
    LangGraph decided a follow-up is needed — the follow-up question.
    """

    answer: AnswerResponse
    quality_score: float
    is_bluff_detected: bool
    reasoning: str
    follow_up_question: QuestionResponse | None = None


class EvaluationResponse(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    overall_score: float
    technical_score: float
    communication_score: float
    recommendation: str
    strengths: str
    gaps: str
    bluff_summary: str
    full_report: str
    created_at: datetime

    model_config = {"from_attributes": True}
