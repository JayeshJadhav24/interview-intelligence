import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from ai_pipeline.interview_graph import InterviewState, get_interview_graph
from app.exceptions import ConflictError, ForbiddenError, NotFoundError
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
