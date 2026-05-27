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

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from ai_pipeline import evaluator
from app.config import get_settings
from app.exceptions import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ServiceUnavailableError,
)
from app.models.session import SessionStatus
from app.repositories.answer import AnswerRepository
from app.repositories.evaluation import EvaluationRepository
from app.repositories.question import QuestionRepository
from app.repositories.session import SessionRepository
from app.schemas.interview import EvaluationResponse

logger = logging.getLogger(__name__)


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
    try:
        report = await evaluator.evaluate_session(
            job_role=session.job_role,
            candidate_profile=session.resume_text[:2000] if session.resume_text else "N/A",
            qa_pairs=qa_pairs,
        )
        report_payload = report.model_dump()
    except Exception as exc:
        logger.exception("AI evaluation report generation failed for session %s", session_id)
        settings = get_settings()
        is_dev_fallback_enabled = (
            settings.environment == "development" and settings.enable_dev_ai_fallback
        )
        if not is_dev_fallback_enabled:
            detail = (
                "AI service authentication failed. Please verify DIAL_API_KEY and Dial access."
                if "AuthenticationError" in str(type(exc)) or "Bad Authorization header" in str(exc)
                else (
                    "Unable to generate evaluation right now. "
                    "Please verify AI service connectivity/API key and retry."
                )
            )
            raise ServiceUnavailableError(detail) from exc

        logger.warning(
            "Falling back to deterministic report generation for session %s (development mode)",
            session_id,
        )

        scored_answers = [
            a.quality_score for a in answers_by_qid.values() if a.quality_score is not None
        ]
        avg_quality = sum(scored_answers) / len(scored_answers) if scored_answers else 0.35
        technical_score = round(max(1.0, min(10.0, avg_quality * 10)), 1)

        answered_texts = [
            a.text for a in answers_by_qid.values() if a.text and a.text != "(no answer submitted)"
        ]
        avg_word_count = (
            sum(len(text.split()) for text in answered_texts) / len(answered_texts)
            if answered_texts
            else 8
        )
        communication_score = round(max(1.0, min(10.0, avg_word_count / 4)), 1)

        overall_score = round((technical_score + communication_score) / 2, 1)
        recommendation = "hire" if overall_score >= 7.0 else "no_hire"

        bluff_count = len([a for a in answers_by_qid.values() if a.is_bluff_detected])
        strengths = (
            "Shows practical understanding with reasonably structured responses."
            if overall_score >= 7.0
            else "Demonstrates baseline understanding in parts of the interview."
        )
        gaps = "Provide deeper technical detail, concrete metrics, and clearer trade-off reasoning."
        bluff_summary = (
            f"{bluff_count} potential bluff signal(s) detected across submitted answers."
            if bluff_count > 0
            else "No explicit bluff signals detected in the submitted answers."
        )
        full_report = (
            "Fallback evaluation report generated in development mode because "
            "AI service was unreachable. "
            "Use this report for UI/testing flow only; scores are heuristic."
        )

        report_payload = {
            "overall_score": overall_score,
            "technical_score": technical_score,
            "communication_score": communication_score,
            "recommendation": recommendation,
            "strengths": strengths,
            "gaps": gaps,
            "bluff_summary": bluff_summary,
            "full_report": full_report,
        }

    # 6. Upsert evaluation row
    eval_repo = EvaluationRepository(db)
    evaluation = await eval_repo.upsert(session_id, report_payload)

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
