import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.question import Question
from app.repositories.base import BaseRepository


class QuestionRepository(BaseRepository[Question]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Question, session)

    async def get_by_session(self, session_id: uuid.UUID) -> list[Question]:
        result = await self._session.execute(
            select(Question).where(Question.session_id == session_id).order_by(Question.order_index)
        )
        return list(result.scalars().all())

    async def get_by_id_and_session(
        self, question_id: uuid.UUID, session_id: uuid.UUID
    ) -> Question | None:
        result = await self._session.execute(
            select(Question).where(
                Question.id == question_id,
                Question.session_id == session_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_max_order_index(self, session_id: uuid.UUID) -> int:
        result = await self._session.execute(
            select(Question.order_index)
            .where(Question.session_id == session_id)
            .order_by(Question.order_index.desc())
            .limit(1)
        )
        return result.scalar_one_or_none() or 0

    async def bulk_create(self, questions_data: list[dict]) -> list[Question]:
        questions = [Question(**data) for data in questions_data]
        for q in questions:
            self._session.add(q)
        await self._session.flush()
        return questions
