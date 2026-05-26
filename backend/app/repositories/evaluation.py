import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.evaluation import Evaluation
from app.repositories.base import BaseRepository


class EvaluationRepository(BaseRepository[Evaluation]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Evaluation, session)

    async def get_by_session(self, session_id: uuid.UUID) -> Evaluation | None:
        result = await self._session.execute(
            select(Evaluation).where(Evaluation.session_id == session_id)
        )
        return result.scalar_one_or_none()

    async def upsert(self, session_id: uuid.UUID, data: dict[str, Any]) -> Evaluation:
        """Create or update the evaluation row for a session."""
        evaluation = await self.get_by_session(session_id)
        if evaluation:
            for key, value in data.items():
                setattr(evaluation, key, value)
        else:
            evaluation = Evaluation(session_id=session_id, **data)
            self._session.add(evaluation)
        await self._session.flush()
        await self._session.refresh(evaluation)
        return evaluation
