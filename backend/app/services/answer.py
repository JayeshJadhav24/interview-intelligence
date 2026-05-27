import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from ai_pipeline.interview_graph import InterviewState, get_interview_graph
from app.config import get_settings
from app.exceptions import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ServiceUnavailableError,
)
from app.models.question import DifficultyLevel, QuestionType
from app.repositories.answer import AnswerRepository
from app.repositories.question import QuestionRepository
from app.repositories.session import SessionRepository
from app.schemas.interview import (
    AnswerCreate,
    AnswerResponse,
    QuestionResponse,
    SubmitAnswerResponse,
)

logger = logging.getLogger(__name__)


async def submit_answer(
    db: AsyncSession,
    session_id: uuid.UUID,
    question_id: uuid.UUID,
    user_id: uuid.UUID,
    data: AnswerCreate,
) -> SubmitAnswerResponse:
    session_repo = SessionRepository(db)
    session = await session_repo.get_by_id(session_id)
    if not session:
        raise NotFoundError("Session")
    if session.user_id != user_id:
        raise ForbiddenError()

    question_repo = QuestionRepository(db)
    question = await question_repo.get_by_id_and_session(question_id, session_id)
    if not question:
        raise NotFoundError("Question")

    answer_repo = AnswerRepository(db)
    if await answer_repo.get_by_question_id(question_id):
        raise ConflictError("Answer already submitted for this question")

    answer = await answer_repo.create(
        question_id=question_id,
        text=data.text,
        quality_score=None,
        is_bluff_detected=False,
        follow_up_generated=False,
    )

    session_questions = await question_repo.get_by_session(session_id)
    answers_by_qid = await answer_repo.get_by_question_ids([q.id for q in session_questions])

    # Build interview memory in chronological order for contextual evaluation.
    history_questions: list[dict[str, str]] = []
    history_answers: list[dict[str, str]] = []
    history_evals: list[dict[str, str | float | bool | None]] = []
    current_index = 0

    for q in session_questions:
        candidate_answer = answers_by_qid.get(q.id)
        if candidate_answer is None:
            continue

        history_questions.append(
            {
                "id": str(q.id),
                "text": q.text,
                "type": q.question_type.value,
                "difficulty": q.difficulty.value,
            }
        )
        history_answers.append({"text": candidate_answer.text})

        if q.id == question_id:
            current_index = len(history_questions) - 1
        elif candidate_answer.quality_score is not None:
            history_evals.append(
                {
                    "question_id": str(q.id),
                    "quality_score": candidate_answer.quality_score,
                    "is_bluff_detected": candidate_answer.is_bluff_detected,
                    "needs_follow_up": bool(candidate_answer.follow_up_generated),
                    "reasoning": "Historical answer in session context",
                    "follow_up_question": None,
                }
            )

    # ── 5. Run the LangGraph evaluation ──────────────────────────────────────
    state: InterviewState = {
        "session_id": str(session_id),
        "questions": history_questions,
        "current_index": current_index,
        "answers": history_answers,
        "evaluations": history_evals,
        "follow_up_count": 0,
        "max_follow_ups": 2,
        "finished": False,
    }

    try:
        result_state: InterviewState = await get_interview_graph().ainvoke(state)
        evaluation = result_state["evaluations"][-1]
    except Exception as exc:
        logger.exception(
            "AI evaluation failed while submitting answer for session %s, question %s",
            session_id,
            question_id,
        )
        settings = get_settings()
        is_dev_fallback_enabled = (
            settings.environment == "development" and settings.enable_dev_ai_fallback
        )
        if not is_dev_fallback_enabled:
            detail = (
                "AI service authentication failed. Please verify DIAL_API_KEY and Dial access."
                if "AuthenticationError" in str(type(exc)) or "Bad Authorization header" in str(exc)
                else (
                    "Unable to evaluate the answer right now. "
                    "Please verify AI service connectivity/API key and retry."
                )
            )
            raise ServiceUnavailableError(detail) from exc

        logger.warning(
            (
                "Falling back to deterministic answer scoring for session %s, "
                "question %s (development mode)"
            ),
            session_id,
            question_id,
        )
        answered_so_far = max(0, len(history_answers) - 1)
        previous_scores = [
            float(ev["quality_score"])
            for ev in history_evals
            if isinstance(ev.get("quality_score"), float)
        ]

        words = data.text.split()
        word_count = len(words)
        lower_text = data.text.lower()

        score = 0.35 + min(word_count, 180) / 220
        if any(ch.isdigit() for ch in data.text):
            score += 0.08  # measurable detail
        if any(k in lower_text for k in ["because", "trade-off", "latency", "throughput", "index"]):
            score += 0.08  # technical reasoning signals
        if word_count < 20:
            score -= 0.2  # too brief
        if previous_scores:
            score = (score * 0.75) + (sum(previous_scores) / len(previous_scores) * 0.25)

        quality_score = round(max(0.1, min(0.95, score)), 2)
        bluff_keywords = [
            "i know everything",
            "never had any failures",
            "100% perfect",
            "expert in all",
        ]
        is_bluff_detected = any(kw in lower_text for kw in bluff_keywords)
        needs_follow_up = quality_score < 0.5 or is_bluff_detected
        follow_up_question = (
            (
                "Can you walk through one concrete project example with the exact "
                "stack, challenges, and trade-offs?"
            )
            if needs_follow_up
            else None
        )
        evaluation = {
            "quality_score": quality_score,
            "is_bluff_detected": is_bluff_detected,
            "reasoning": (
                "Fallback scoring in development mode based on specificity, technical reasoning, "
                f"and interview consistency across {answered_so_far} prior answered question(s)."
            ),
            "needs_follow_up": needs_follow_up,
            "follow_up_question": follow_up_question,
        }

    # ── 6. Update Answer with evaluation results ──────────────────────────────
    answer.quality_score = evaluation["quality_score"]
    answer.is_bluff_detected = evaluation["is_bluff_detected"]

    # ── 7. Optionally persist a follow-up Question ────────────────────────────
    follow_up_question_row = None

    if evaluation["needs_follow_up"] and evaluation.get("follow_up_question"):
        answer.follow_up_generated = True
        max_order = await question_repo.get_max_order_index(session_id)
        follow_up_question_row = await question_repo.create(
            session_id=session_id,
            parent_question_id=question_id,
            text=evaluation["follow_up_question"],
            question_type=QuestionType.FOLLOW_UP,
            difficulty=DifficultyLevel.MEDIUM,
            order_index=max_order + 1,
        )

    await db.commit()
    await db.refresh(answer)

    follow_up_response: QuestionResponse | None = None
    if follow_up_question_row:
        await db.refresh(follow_up_question_row)
        follow_up_response = QuestionResponse.model_validate(follow_up_question_row)

    return SubmitAnswerResponse(
        answer=AnswerResponse.model_validate(answer),
        quality_score=evaluation["quality_score"],
        is_bluff_detected=evaluation["is_bluff_detected"],
        reasoning=evaluation["reasoning"],
        follow_up_question=follow_up_response,
    )
