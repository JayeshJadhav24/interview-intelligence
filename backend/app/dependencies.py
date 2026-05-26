import uuid
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.exceptions import UnauthorizedError
from app.models.user import User
from app.repositories.user import UserRepository
from app.services.auth import decode_token

_bearer = HTTPBearer()

DbDep = Annotated[AsyncSession, Depends(get_db)]


async def get_current_user(
    db: DbDep,
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
) -> User:
    user_id = decode_token(credentials.credentials, expected_type="access")
    repo = UserRepository(db)
    user = await repo.get_by_id(uuid.UUID(user_id))
    if not user:
        raise UnauthorizedError()
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
