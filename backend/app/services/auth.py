from datetime import UTC, datetime, timedelta
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.exceptions import ConflictError, UnauthorizedError
from app.models.user import User
from app.repositories.user import UserRepository
from app.schemas.auth import TokenResponse, UserCreate

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return _pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_context.verify(plain, hashed)


def _create_token(data: dict[str, Any], expires_delta: timedelta) -> str:
    settings = get_settings()
    payload = data.copy()
    payload["exp"] = datetime.now(UTC) + expires_delta
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_tokens(user_id: str) -> TokenResponse:
    settings = get_settings()
    access_token = _create_token(
        {"sub": user_id, "type": "access"},
        timedelta(minutes=settings.access_token_expire_minutes),
    )
    refresh_token = _create_token(
        {"sub": user_id, "type": "refresh"},
        timedelta(days=settings.refresh_token_expire_days),
    )
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


def decode_token(token: str, expected_type: str = "access") -> str:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise UnauthorizedError("Token is invalid or expired") from exc

    if payload.get("type") != expected_type:
        raise UnauthorizedError("Wrong token type")

    sub: str | None = payload.get("sub")
    if sub is None:
        raise UnauthorizedError("Token missing subject")
    return sub


async def signup(db: AsyncSession, data: UserCreate) -> tuple[User, TokenResponse]:
    repo = UserRepository(db)
    existing = await repo.get_by_email(data.email)
    if existing:
        raise ConflictError("Email already registered")

    user = await repo.create(
        email=data.email,
        hashed_password=hash_password(data.password),
        full_name=data.full_name,
    )
    await db.commit()
    tokens = create_tokens(str(user.id))
    return user, tokens


async def login(db: AsyncSession, email: str, password: str) -> tuple[User, TokenResponse]:
    repo = UserRepository(db)
    user = await repo.get_by_email(email)
    if not user or not verify_password(password, user.hashed_password):
        raise UnauthorizedError()

    tokens = create_tokens(str(user.id))
    return user, tokens


async def refresh(db: AsyncSession, refresh_token: str) -> TokenResponse:
    user_id = decode_token(refresh_token, expected_type="refresh")
    repo = UserRepository(db)
    user = await repo.get_by_id(__import__("uuid").UUID(user_id))
    if not user:
        raise UnauthorizedError()
    return create_tokens(str(user.id))
