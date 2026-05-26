from sqlalchemy.ext.asyncio import AsyncSession

from app.models.skill import Skill
from app.repositories.base import BaseRepository


class SkillRepository(BaseRepository[Skill]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Skill, session)

    async def bulk_create(self, skills_data: list[dict]) -> list[Skill]:
        skills = [Skill(**data) for data in skills_data]
        for s in skills:
            self._session.add(s)
        await self._session.flush()
        return skills
