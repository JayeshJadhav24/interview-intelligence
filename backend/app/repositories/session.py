import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.session import InterviewSession
from app.repositories.base import BaseRepository


class SessionRepository(BaseRepository[InterviewSession]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(InterviewSession, session)

    async def get_by_user(self, user_id: uuid.UUID) -> list[InterviewSession]:
        result = await self._session.execute(
            select(InterviewSession)
            .where(InterviewSession.user_id == user_id)
            .order_by(InterviewSession.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_with_skills(self, session_id: uuid.UUID) -> InterviewSession | None:
        result = await self._session.execute(
            select(InterviewSession)
            .where(InterviewSession.id == session_id)
            .options(selectinload(InterviewSession.skills))
        )
        return result.scalar_one_or_none()

    async def get_full(self, session_id: uuid.UUID) -> InterviewSession | None:
        result = await self._session.execute(
            select(InterviewSession)
            .where(InterviewSession.id == session_id)
            .options(
                selectinload(InterviewSession.skills),
                selectinload(InterviewSession.questions),
                selectinload(InterviewSession.evaluation),
            )
        )
        return result.scalar_one_or_none()
