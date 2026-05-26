import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.answer import Answer
from app.repositories.base import BaseRepository


class AnswerRepository(BaseRepository[Answer]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Answer, session)

    async def get_by_question_id(self, question_id: uuid.UUID) -> Answer | None:
        result = await self._session.execute(
            select(Answer).where(Answer.question_id == question_id)
        )
        return result.scalar_one_or_none()

    async def get_by_question_ids(self, question_ids: list[uuid.UUID]) -> dict[uuid.UUID, Answer]:
        result = await self._session.execute(
            select(Answer).where(Answer.question_id.in_(question_ids))
        )
        return {a.question_id: a for a in result.scalars().all()}
