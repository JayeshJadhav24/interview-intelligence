import uuid

from fastapi import APIRouter, File, Form, UploadFile

from app.dependencies import CurrentUser, DbDep
from app.schemas.interview import SessionCreate, SessionResponse, SkillResponse
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
