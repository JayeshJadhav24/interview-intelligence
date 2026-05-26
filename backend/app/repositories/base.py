import uuid
from typing import Any, Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import Base

ModelT = TypeVar("ModelT", bound=Base)  # type: ignore[type-arg]


class BaseRepository(Generic[ModelT]):
    def __init__(self, model: type[ModelT], session: AsyncSession) -> None:
        self._model = model
        self._session = session

    async def get_by_id(self, id: uuid.UUID) -> ModelT | None:
        result = await self._session.get(self._model, id)
        return result

    async def get_all(self) -> list[ModelT]:
        result = await self._session.execute(select(self._model))
        return list(result.scalars().all())

    async def create(self, **kwargs: Any) -> ModelT:
        instance = self._model(**kwargs)
        self._session.add(instance)
        await self._session.flush()
        await self._session.refresh(instance)
        return instance

    async def delete(self, instance: ModelT) -> None:
        await self._session.delete(instance)
        await self._session.flush()
