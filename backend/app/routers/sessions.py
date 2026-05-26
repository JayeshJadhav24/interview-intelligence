import uuid

from fastapi import APIRouter, File, Form, UploadFile

from app.dependencies import CurrentUser, DbDep
from app.schemas.interview import (
    AnswerCreate,
    EvaluationResponse,
    QuestionResponse,
    SessionCreate,
    SessionResponse,
    SkillResponse,
    SubmitAnswerResponse,
)
from app.services import answer as answer_service
from app.services import evaluation as evaluation_service
from app.services import session as session_service

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("", response_model=SessionResponse, status_code=201)
async def create_session(
    db: DbDep,
    current_user: CurrentUser,
    job_role: str = Form(...),
    jd_text: str | None = Form(default=None),
    resume_text: str | None = Form(default=None),
    resume_file: UploadFile | None = File(default=None),  # noqa: B008
) -> SessionResponse:
    data = SessionCreate(job_role=job_role, resume_text=resume_text, jd_text=jd_text)
    session = await session_service.create_session(db, current_user.id, data, resume_file)
    return SessionResponse.model_validate(session)


@router.get("", response_model=list[SessionResponse])
async def list_sessions(db: DbDep, current_user: CurrentUser) -> list[SessionResponse]:
    return await session_service.list_sessions(db, current_user.id)


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: uuid.UUID, db: DbDep, current_user: CurrentUser
) -> SessionResponse:
    session = await session_service.get_session(db, session_id, current_user.id)
    return SessionResponse.model_validate(session)


@router.post("/{session_id}/process", response_model=list[SkillResponse])
async def process_session(
    session_id: uuid.UUID, db: DbDep, current_user: CurrentUser
) -> list[SkillResponse]:
    return await session_service.process_session(db, session_id, current_user.id)


@router.delete("/{session_id}", status_code=204)
async def delete_session(session_id: uuid.UUID, db: DbDep, current_user: CurrentUser) -> None:
    await session_service.delete_session(db, session_id, current_user.id)


@router.get("/{session_id}/questions", response_model=list[QuestionResponse])
async def list_questions(
    session_id: uuid.UUID, db: DbDep, current_user: CurrentUser
) -> list[QuestionResponse]:
    """Return all questions for a session in order_index order."""
    return await session_service.list_questions(db, session_id, current_user.id)


@router.post(
    "/{session_id}/questions/{question_id}/answer",
    response_model=SubmitAnswerResponse,
    status_code=201,
)
async def submit_answer(
    session_id: uuid.UUID,
    question_id: uuid.UUID,
    data: AnswerCreate,
    db: DbDep,
    current_user: CurrentUser,
) -> SubmitAnswerResponse:
    """Submit a candidate's answer. Triggers LangGraph evaluation + optional follow-up."""
    return await answer_service.submit_answer(db, session_id, question_id, current_user.id, data)


@router.post("/{session_id}/evaluate", response_model=EvaluationResponse, status_code=201)
async def evaluate_session(
    session_id: uuid.UUID, db: DbDep, current_user: CurrentUser
) -> EvaluationResponse:
    """Generate a hire/no-hire evaluation report for the completed session."""
    return await evaluation_service.generate_evaluation(db, session_id, current_user.id)


@router.get("/{session_id}/evaluation", response_model=EvaluationResponse)
async def get_evaluation(
    session_id: uuid.UUID, db: DbDep, current_user: CurrentUser
) -> EvaluationResponse:
    """Retrieve the latest evaluation report for a session."""
    return await evaluation_service.get_evaluation(db, session_id, current_user.id)
