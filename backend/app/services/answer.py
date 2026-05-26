"""
Answer submission service.

Orchestrates the LangGraph interview graph for a single answer:
  1. Fetch the question from DB (verify ownership via session)
  2. Persist the Answer row
  3. Build a minimal InterviewState and invoke the graph
  4. Persist the evaluation result back to the Answer row
  5. If a follow-up is needed, persist a new Question row and return it
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_pipeline.interview_graph import InterviewState, get_interview_graph
from app.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.models.answer import Answer
from app.models.question import DifficultyLevel, Question, QuestionType
from app.models.session import InterviewSession
from app.schemas.interview import (
    AnswerCreate,
    AnswerResponse,
    QuestionResponse,
    SubmitAnswerResponse,
)


async def submit_answer(
    db: AsyncSession,
    session_id: uuid.UUID,
    question_id: uuid.UUID,
    user_id: uuid.UUID,
    data: AnswerCreate,
) -> SubmitAnswerResponse:
    # ── 1. Verify the session belongs to this user ────────────────────────────
    session_result = await db.execute(
        select(InterviewSession).where(InterviewSession.id == session_id)
    )
    session: InterviewSession | None = session_result.scalar_one_or_none()
    if not session:
        raise NotFoundError("Session")
    if session.user_id != user_id:
        raise ForbiddenError()

    # ── 2. Fetch the question ─────────────────────────────────────────────────
    q_result = await db.execute(
        select(Question).where(
            Question.id == question_id,
            Question.session_id == session_id,
        )
    )
    question: Question | None = q_result.scalar_one_or_none()
    if not question:
        raise NotFoundError("Question")

    # ── 3. Guard: only one answer per question ────────────────────────────────
    existing = await db.execute(select(Answer).where(Answer.question_id == question_id))
    if existing.scalar_one_or_none():
        raise ConflictError("Answer already submitted for this question")

    # ── 4. Persist the Answer (unscored for now) ──────────────────────────────
    answer = Answer(
        question_id=question_id,
        text=data.text,
        quality_score=None,
        is_bluff_detected=False,
        follow_up_generated=False,
    )
    db.add(answer)
    await db.flush()  # get answer.id without committing yet

    # ── 5. Run the LangGraph evaluation ──────────────────────────────────────
    state: InterviewState = {
        "session_id": str(session_id),
        "questions": [
            {
                "id": str(question.id),
                "text": question.text,
                "type": question.question_type.value,
                "difficulty": question.difficulty.value,
            }
        ],
        "current_index": 0,
        "answers": [{"text": data.text}],
        "evaluations": [],
        "follow_up_count": 0,
        "max_follow_ups": 2,
        "finished": False,
    }

    result_state: InterviewState = await get_interview_graph().ainvoke(state)
    evaluation = result_state["evaluations"][0]

    # ── 6. Update Answer with evaluation results ──────────────────────────────
    answer.quality_score = evaluation["quality_score"]
    answer.is_bluff_detected = evaluation["is_bluff_detected"]

    # ── 7. Optionally persist a follow-up Question ────────────────────────────
    follow_up_question_row: Question | None = None

    if evaluation["needs_follow_up"] and evaluation.get("follow_up_question"):
        answer.follow_up_generated = True

        # Find highest order_index in this session to place follow-up after current
        max_order_result = await db.execute(
            select(Question.order_index)
            .where(Question.session_id == session_id)
            .order_by(Question.order_index.desc())
            .limit(1)
        )
        max_order = max_order_result.scalar_one_or_none() or 0

        follow_up_question_row = Question(
            session_id=session_id,
            parent_question_id=question_id,
            text=evaluation["follow_up_question"],
            question_type=QuestionType.FOLLOW_UP,
            difficulty=DifficultyLevel.MEDIUM,
            order_index=max_order + 1,
        )
        db.add(follow_up_question_row)

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
