"""
Evaluation service — orchestrates the full session report.

Steps:
  1. Load session via SessionRepository (verify ownership)
  2. Load questions via QuestionRepository
  3. Load answers via AnswerRepository
  4. Call evaluator.evaluate_session()
  5. Upsert Evaluation row via EvaluationRepository
  6. Mark session status as COMPLETED
  7. Return EvaluationResponse
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from ai_pipeline import evaluator
from app.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.models.session import SessionStatus
from app.repositories.answer import AnswerRepository
from app.repositories.evaluation import EvaluationRepository
from app.repositories.question import QuestionRepository
from app.repositories.session import SessionRepository
from app.schemas.interview import EvaluationResponse


async def generate_evaluation(
    db: AsyncSession,
    session_id: uuid.UUID,
    user_id: uuid.UUID,
) -> EvaluationResponse:
    # 1. Verify ownership
    session_repo = SessionRepository(db)
    session = await session_repo.get_by_id(session_id)
    if not session:
        raise NotFoundError("Session")
    if session.user_id != user_id:
        raise ForbiddenError()

    # 2. Load questions
    question_repo = QuestionRepository(db)
    questions = await question_repo.get_by_session(session_id)
    if not questions:
        raise ConflictError("No questions found — run /process first")

    # 3. Load answers keyed by question_id
    answer_repo = AnswerRepository(db)
    answers_by_qid = await answer_repo.get_by_question_ids([q.id for q in questions])

    # 4. Build qa_pairs for the AI evaluator
    qa_pairs: list[dict] = [
        {
            "question": q.text,
            "answer": answers_by_qid[q.id].text
            if q.id in answers_by_qid
            else "(no answer submitted)",
            "quality_score": answers_by_qid[q.id].quality_score if q.id in answers_by_qid else 0.0,
            "is_bluff_detected": answers_by_qid[q.id].is_bluff_detected
            if q.id in answers_by_qid
            else False,
        }
        for q in questions
    ]

    # 5. Call AI evaluator
    report = await evaluator.evaluate_session(
        job_role=session.job_role,
        candidate_profile=session.resume_text[:2000] if session.resume_text else "N/A",
        qa_pairs=qa_pairs,
    )

    # 6. Upsert evaluation row
    eval_repo = EvaluationRepository(db)
    evaluation = await eval_repo.upsert(session_id, report.model_dump())

    # 7. Mark session completed
    session.status = SessionStatus.COMPLETED
    await db.commit()
    await db.refresh(evaluation)

    return EvaluationResponse.model_validate(evaluation)


async def get_evaluation(
    db: AsyncSession,
    session_id: uuid.UUID,
    user_id: uuid.UUID,
) -> EvaluationResponse:
    session_repo = SessionRepository(db)
    session = await session_repo.get_by_id(session_id)
    if not session:
        raise NotFoundError("Session")
    if session.user_id != user_id:
        raise ForbiddenError()

    eval_repo = EvaluationRepository(db)
    evaluation = await eval_repo.get_by_session(session_id)
    if not evaluation:
        raise NotFoundError("Evaluation")
    return EvaluationResponse.model_validate(evaluation)
