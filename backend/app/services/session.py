import logging
import uuid

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_pipeline import jd_analyzer, question_generator, resume_parser
from app.config import get_settings
from app.exceptions import ForbiddenError, NotFoundError, ServiceUnavailableError
from app.models.question import DifficultyLevel, QuestionType
from app.models.session import InterviewSession, SessionStatus
from app.repositories.question import QuestionRepository
from app.repositories.session import SessionRepository
from app.repositories.skill import SkillRepository
from app.schemas.interview import QuestionResponse, SessionCreate, SessionResponse, SkillResponse
from app.services.pdf import read_and_validate_pdf

logger = logging.getLogger(__name__)


def _build_fallback_skills(resume_text: str | None, jd_text: str | None) -> list[dict[str, object]]:
    source = f"{resume_text or ''} {jd_text or ''}".lower()
    keyword_map = [
        ("python", "Python", "backend"),
        ("fastapi", "FastAPI", "backend"),
        ("django", "Django", "backend"),
        ("postgres", "PostgreSQL", "database"),
        ("sql", "SQL", "database"),
        ("docker", "Docker", "devops"),
        ("kubernetes", "Kubernetes", "devops"),
        ("react", "React", "frontend"),
        ("next.js", "Next.js", "frontend"),
    ]

    skills: list[dict[str, object]] = [
        {
            "name": name,
            "category": category,
            "confidence_score": 0.65,
            "years_experience": None,
            "is_bluff_risk": False,
        }
        for token, name, category in keyword_map
        if token in source
    ]

    if not skills and source.strip():
        skills.append(
            {
                "name": "Problem Solving",
                "category": "general",
                "confidence_score": 0.5,
                "years_experience": None,
                "is_bluff_risk": False,
            }
        )

    return skills


def _build_fallback_questions(job_role: str) -> list[dict[str, object]]:
    role = job_role or "this role"
    return [
        # Phase 1 — Warm-up and context setting
        {
            "text": (
                "To start, can you walk me through a project you're most proud of "
                f"that's relevant to {role}?"
            ),
            "question_type": QuestionType.CONCEPTUAL,
            "difficulty": DifficultyLevel.EASY,
        },
        {
            "text": "What architecture decisions did you make in that project, and why?",
            "question_type": QuestionType.CONCEPTUAL,
            "difficulty": DifficultyLevel.EASY,
        },
        # Phase 2 — Core technical evaluation
        {
            "text": (
                "How do you design APIs for reliability, observability, and "
                "backward compatibility?"
            ),
            "question_type": QuestionType.PRACTICAL,
            "difficulty": DifficultyLevel.MEDIUM,
        },
        {
            "text": (
                "What approach do you use for database schema design and query "
                "optimization in production systems?"
            ),
            "question_type": QuestionType.PRACTICAL,
            "difficulty": DifficultyLevel.MEDIUM,
        },
        # Phase 3 — Deep dive / validation
        {
            "text": (
                "Tell me about a challenging bug or outage you handled end-to-end. "
                "How did you isolate the root cause?"
            ),
            "question_type": QuestionType.PRACTICAL,
            "difficulty": DifficultyLevel.HARD,
        },
        {
            "text": (
                "If your service had to scale 10x traffic, what would you change " "first and why?"
            ),
            "question_type": QuestionType.PRACTICAL,
            "difficulty": DifficultyLevel.HARD,
        },
        # Phase 4 — Scenario based
        {
            "text": (
                "Your API latency suddenly doubles in production. "
                "What is your step-by-step debugging plan?"
            ),
            "question_type": QuestionType.PRACTICAL,
            "difficulty": DifficultyLevel.HARD,
        },
        {
            "text": (
                "A deployment caused intermittent failures for one customer segment. "
                "How would you mitigate quickly and investigate safely?"
            ),
            "question_type": QuestionType.PRACTICAL,
            "difficulty": DifficultyLevel.HARD,
        },
        # Phase 5 — Behavioral and bluff validation
        {
            "text": (
                "Describe a time you received critical feedback from a teammate "
                "or manager. What changed afterward?"
            ),
            "question_type": QuestionType.BEHAVIORAL,
            "difficulty": DifficultyLevel.MEDIUM,
        },
        {
            "text": (
                "Pick one technology you claim strong expertise in and explain one "
                "production trade-off you made while using it."
            ),
            "question_type": QuestionType.BLUFF_CHECK,
            "difficulty": DifficultyLevel.HARD,
        },
    ]


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
    lock_result = await db.execute(
        select(InterviewSession).where(InterviewSession.id == session_id).with_for_update()
    )
    session = lock_result.scalar_one_or_none()

    if not session:
        raise NotFoundError("Session")
    if session.user_id != user_id:
        raise ForbiddenError()

    skills_to_create: list[dict] = []
    parse_result = None
    skills_persisted = False
    skill_repo = SkillRepository(db)
    question_repo = QuestionRepository(db)

    # Idempotency guard: if questions already exist, this session is already processed.
    existing_questions = await question_repo.get_by_session(session_id)
    if existing_questions:
        if session.status == SessionStatus.PENDING:
            session.status = SessionStatus.IN_PROGRESS
            await db.commit()
            await db.refresh(session)

        updated = await repo.get_with_skills(session_id)
        if not updated:
            return []
        return [SkillResponse.model_validate(s) for s in updated.skills]

    existing = await repo.get_with_skills(session_id)
    existing_skill_names = {
        s.name.strip().lower() for s in (existing.skills if existing else []) if s.name
    }

    try:
        if session.resume_text:
            parse_result = await resume_parser.parse_resume_from_text(session.resume_text)
            skills_to_create.extend(
                [
                    {
                        "session_id": session_id,
                        "name": skill.name,
                        "category": skill.category,
                        "confidence_score": skill.confidence_score,
                        "years_experience": skill.years_experience,
                        "is_bluff_risk": skill.is_bluff_risk,
                    }
                    for skill in parse_result.skills
                    if skill.name.strip().lower() not in existing_skill_names
                ]
            )

        # Persist skills
        if skills_to_create:
            await skill_repo.bulk_create(skills_to_create)
            skills_persisted = True

        # ── Generate questions if we have both resume + JD ────────────────────────
        if parse_result and session.jd_text:
            jd_result = await jd_analyzer.analyze_jd(session.jd_text)
            question_batch = await question_generator.generate_questions(parse_result, jd_result)

            seen_question_texts: set[str] = set()
            unique_question_payloads: list[dict[str, object]] = []
            for q in question_batch.questions:
                normalized = q.text.strip().lower()
                if normalized in seen_question_texts:
                    continue
                seen_question_texts.add(normalized)
                unique_question_payloads.append(
                    {
                        "session_id": session_id,
                        "text": q.text,
                        "question_type": q.question_type,
                        "difficulty": q.difficulty,
                    }
                )

            await question_repo.bulk_create(
                [
                    {
                        **q,
                        "order_index": idx,
                    }
                    for idx, q in enumerate(unique_question_payloads)
                ]
            )
    except Exception as exc:
        logger.exception("AI pipeline failed while processing session %s", session_id)
        settings = get_settings()
        is_dev_fallback_enabled = (
            settings.environment == "development" and settings.enable_dev_ai_fallback
        )
        if not is_dev_fallback_enabled:
            detail = (
                "AI service authentication failed. Please verify DIAL_API_KEY and Dial access."
                if "AuthenticationError" in str(type(exc)) or "Bad Authorization header" in str(exc)
                else (
                    "Unable to process this interview right now. "
                    "Please verify AI service connectivity/API key and retry."
                )
            )
            raise ServiceUnavailableError(detail) from exc

        logger.warning(
            "Falling back to deterministic interview setup for session %s (development mode)",
            session_id,
        )

        if not skills_to_create:
            skills_to_create.extend(_build_fallback_skills(session.resume_text, session.jd_text))

        if skills_to_create and not skills_persisted:
            await skill_repo.bulk_create(
                [{"session_id": session_id, **skill} for skill in skills_to_create]
            )

        existing_questions = await question_repo.get_by_session(session_id)
        if not existing_questions:
            fallback_questions = _build_fallback_questions(session.job_role)
            await question_repo.bulk_create(
                [
                    {
                        "session_id": session_id,
                        "text": q["text"],
                        "question_type": q["question_type"],
                        "difficulty": q["difficulty"],
                        "order_index": idx,
                    }
                    for idx, q in enumerate(fallback_questions)
                ]
            )

    session.status = SessionStatus.IN_PROGRESS
    await db.commit()
    await db.refresh(session)

    # Return persisted skills
    updated = await repo.get_with_skills(session_id)
    if not updated:
        return []
    return [SkillResponse.model_validate(s) for s in updated.skills]


async def list_questions(
    db: AsyncSession, session_id: uuid.UUID, user_id: uuid.UUID
) -> list[QuestionResponse]:
    """Return ordered questions for a session, verifying ownership first."""
    await get_session(db, session_id, user_id)  # raises 404/403
    repo = QuestionRepository(db)
    questions = await repo.get_by_session(session_id)

    # Defensive dedupe for sessions affected by duplicate generation races.
    seen: set[tuple[str, str, str]] = set()
    unique_questions: list[QuestionResponse] = []
    for q in questions:
        key = (
            q.text.strip().lower(),
            str(q.question_type),
            str(q.difficulty),
        )
        if key in seen:
            continue
        seen.add(key)
        unique_questions.append(QuestionResponse.model_validate(q))

    return unique_questions


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
