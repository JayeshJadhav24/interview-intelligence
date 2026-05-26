import uuid

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from ai_pipeline import jd_analyzer, question_generator, resume_parser
from app.exceptions import ForbiddenError, NotFoundError
from app.models.session import InterviewSession, SessionStatus
from app.repositories.session import SessionRepository
from app.schemas.interview import SessionCreate, SessionResponse, SkillResponse
from app.services.pdf import read_and_validate_pdf


async def create_session(
    db: AsyncSession,
    user_id: uuid.UUID,
    data: SessionCreate,
    resume_file: UploadFile | None = None,
) -> InterviewSession:
    repo = SessionRepository(db)

    resume_text: str | None = data.resume_text
    if resume_file is not None:
        pdf_bytes = await read_and_validate_pdf(resume_file)
        resume_text = resume_parser.extract_text_from_pdf(pdf_bytes)

    session = await repo.create(
        user_id=user_id,
        job_role=data.job_role,
        resume_text=resume_text,
        jd_text=data.jd_text,
        status=SessionStatus.PENDING,
    )
    await db.commit()
    return session


async def process_session(
    db: AsyncSession,
    session_id: uuid.UUID,
    user_id: uuid.UUID,
) -> list[SkillResponse]:
    """Run AI pipeline: parse resume + JD → skills + questions, update status."""
    repo = SessionRepository(db)
    session = await repo.get_by_id(session_id)

    if not session:
        raise NotFoundError("Session")
    if session.user_id != user_id:
        raise ForbiddenError()

    skills_to_create: list[dict] = []
    parse_result = None

    if session.resume_text:
        parse_result = await resume_parser.parse_resume_from_text(session.resume_text)
        for skill in parse_result.skills:
            skills_to_create.append(
                {
                    "session_id": session_id,
                    "name": skill.name,
                    "category": skill.category,
                    "confidence_score": skill.confidence_score,
                    "years_experience": skill.years_experience,
                    "is_bluff_risk": skill.is_bluff_risk,
                }
            )

    # Persist skills via raw ORM (no separate skill repo needed yet)
    from app.models.skill import Skill  # noqa: PLC0415

    for skill_data in skills_to_create:
        db.add(Skill(**skill_data))

    # ── Generate questions if we have both resume + JD ────────────────────────
    if parse_result and session.jd_text:
        from app.models.question import Question  # noqa: PLC0415

        jd_result = await jd_analyzer.analyze_jd(session.jd_text)
        question_batch = await question_generator.generate_questions(parse_result, jd_result)

        for idx, q in enumerate(question_batch.questions):
            db.add(
                Question(
                    session_id=session_id,
                    text=q.text,
                    question_type=q.question_type,
                    difficulty=q.difficulty,
                    order_index=idx,
                )
            )

    session.status = SessionStatus.IN_PROGRESS
    await db.commit()
    await db.refresh(session)

    # Return persisted skills
    updated = await repo.get_with_skills(session_id)
    if not updated:
        return []
    return [SkillResponse.model_validate(s) for s in updated.skills]


async def list_sessions(db: AsyncSession, user_id: uuid.UUID) -> list[SessionResponse]:
    repo = SessionRepository(db)
    sessions = await repo.get_by_user(user_id)
    return [SessionResponse.model_validate(s) for s in sessions]


async def get_session(
    db: AsyncSession, session_id: uuid.UUID, user_id: uuid.UUID
) -> InterviewSession:
    repo = SessionRepository(db)
    session = await repo.get_by_id(session_id)
    if not session:
        raise NotFoundError("Session")
    if session.user_id != user_id:
        raise ForbiddenError()
    return session


async def delete_session(db: AsyncSession, session_id: uuid.UUID, user_id: uuid.UUID) -> None:
    repo = SessionRepository(db)
    session = await repo.get_by_id(session_id)
    if not session:
        raise NotFoundError("Session")
    if session.user_id != user_id:
        raise ForbiddenError()
    await repo.delete(session)
    await db.commit()
