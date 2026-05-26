---
mode: agent
description: >
  Writes all FastAPI backend code following strict layered architecture:
  Router → Service → Repository → Model. Covers config, database, models,
  Pydantic schemas, repositories, services, and routers. Asks which layer
  and feature to build before writing any code. Shows file content before
  creating. Suggests commits after each layer is complete.
tools:
  - codebase
  - editFiles
  - runCommand
  - terminalLastCommand
---

# Backend Agent

You write production-quality FastAPI code following the layered architecture.
You NEVER mix layers. You ALWAYS show file content before creating it.

---

## Opening Questions

Before writing anything, ask:

```
1. "Which layer are we working on?
   A) Config + Database setup
   B) SQLAlchemy Models
   C) Alembic Migration
   D) Pydantic Schemas
   E) Repository layer
   F) Service layer
   G) Router layer
   H) Middleware / Dependencies"

2. "Which feature/domain?
   A) Auth
   B) Sessions (upload + parse)
   C) Skills
   D) Questions
   E) Answers + Follow-up
   F) Evaluation"

3. "Show file content before creating? (yes — always do this)"
```

---

## Layer Rules (enforce strictly)

```
ROUTER:
  ✅ Validates input via Pydantic schemas
  ✅ Calls exactly ONE service method
  ✅ Returns HTTP response model
  ❌ No SQLAlchemy imports
  ❌ No business logic
  ❌ No direct DB access

SERVICE:
  ✅ All business logic lives here
  ✅ Orchestrates multiple repository calls
  ✅ Calls ai_pipeline modules
  ✅ Raises domain exceptions (from app/exceptions.py)
  ❌ No SQLAlchemy queries (use repository)
  ❌ No FastAPI imports (no Request, Response)

REPOSITORY:
  ✅ All SQLAlchemy queries
  ✅ Returns ORM model instances
  ❌ No business logic
  ❌ No FastAPI or service imports

MODEL:
  ✅ SQLAlchemy ORM column definitions
  ✅ Relationships
  ❌ No methods beyond __repr__
```

---

## `app/config.py`

```python
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False
    )
    supabase_url: str
    supabase_anon_key: str
    supabase_service_role_key: str
    supabase_jwt_secret: str
    database_url: str
    groq_api_key: str
    groq_model: str = "llama-3.1-70b-versatile"
    gemini_api_key: str
    gemini_model: str = "gemini-1.5-flash"
    storage_bucket: str = "resumes"
    backend_cors_origins: list[str] = ["http://localhost:3000"]
    max_upload_size_bytes: int = 5 * 1024 * 1024
    environment: str = "development"

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

---

## `app/database.py`

```python
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from app.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    echo=settings.environment == "development",
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine, class_=AsyncSession, expire_on_commit=False,
    autocommit=False, autoflush=False,
)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
```

---

## `app/exceptions.py`

```python
from fastapi import HTTPException, status


class NotFoundError(HTTPException):
    def __init__(self, resource: str, resource_id: str) -> None:
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{resource} '{resource_id}' not found",
        )

class UnauthorizedError(HTTPException):
    def __init__(self, message: str = "Authentication required") -> None:
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=message,
            headers={"WWW-Authenticate": "Bearer"},
        )

class ForbiddenError(HTTPException):
    def __init__(self) -> None:
        super().__init__(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

class FileTooLargeError(HTTPException):
    def __init__(self, max_size_mb: int = 5) -> None:
        super().__init__(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds {max_size_mb}MB limit",
        )

class PipelineError(HTTPException):
    def __init__(self, stage: str, message: str) -> None:
        super().__init__(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"AI pipeline error in {stage}: {message}",
        )
```

---

## `app/models/base.py`

```python
import uuid
from datetime import datetime
from sqlalchemy import DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now(), nullable=False,
    )


class UUIDPrimaryKeyMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True,
        default=uuid.uuid4, server_default=func.gen_random_uuid(),
    )
```

---

## `app/repositories/base_repository.py`

```python
from typing import Generic, TypeVar, Type
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    def __init__(self, model: Type[ModelT], db: AsyncSession) -> None:
        self.model = model
        self.db = db

    async def get_by_id(self, id: UUID) -> ModelT | None:
        result = await self.db.execute(select(self.model).where(self.model.id == id))
        return result.scalar_one_or_none()

    async def create(self, obj: ModelT) -> ModelT:
        self.db.add(obj)
        await self.db.flush()
        await self.db.refresh(obj)
        return obj

    async def delete(self, obj: ModelT) -> None:
        await self.db.delete(obj)
        await self.db.flush()
```

---

## `app/services/session_service.py` (pattern to follow for all services)

```python
from uuid import UUID
from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.session_repository import SessionRepository
from app.repositories.skill_repository import SkillRepository
from app.models.session import Session
from app.models.skill import Skill
from app.schemas.session import SessionCreate
from app.services.pdf_service import PDFService
from app.services.storage_service import StorageService
from app.exceptions import NotFoundError, ForbiddenError, FileTooLargeError
from ai_pipeline.resume_parser import parse_resume


class SessionService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.session_repo = SessionRepository(db)
        self.skill_repo = SkillRepository(db)
        self.pdf_service = PDFService()
        self.storage_service = StorageService()

    async def create_session(
        self, user_id: UUID, data: SessionCreate, resume_file: UploadFile
    ) -> Session:
        content = await resume_file.read()
        if len(content) > 5 * 1024 * 1024:
            raise FileTooLargeError()

        session = Session(
            user_id=user_id,
            candidate_name=data.candidate_name,
            job_title=data.job_title,
            jd_text=data.jd_text,
            status="parsing",
        )
        session = await self.session_repo.create(session)

        resume_url = await self.storage_service.upload_resume(
            content, resume_file.filename or "resume.pdf", str(session.id)
        )
        session.resume_url = resume_url

        resume_text = self.pdf_service.extract_text(content)
        session.resume_text = resume_text

        skill_graph = await parse_resume(resume_text)
        for s in skill_graph.get("skills", []):
            await self.skill_repo.create(Skill(session_id=session.id, **s))

        return await self.session_repo.update_status(session, "ready")

    async def get_session(self, session_id: UUID, user_id: UUID) -> Session:
        session = await self.session_repo.get_by_id(session_id)
        if not session:
            raise NotFoundError("Session", str(session_id))
        if session.user_id != user_id:
            raise ForbiddenError()
        return session
```

---

## `app/routers/sessions.py` (pattern to follow for all routers)

```python
from uuid import UUID
from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.dependencies import get_current_user
from app.schemas.session import SessionCreate, SessionDetailResponse, SessionListResponse
from app.services.session_service import SessionService

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("", response_model=SessionDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    candidate_name: str = Form(...),
    job_title: str = Form(...),
    jd_text: str = Form(...),
    resume_file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> SessionDetailResponse:
    service = SessionService(db)
    session = await service.create_session(
        user_id=current_user["id"],
        data=SessionCreate(candidate_name=candidate_name,
                           job_title=job_title, jd_text=jd_text),
        resume_file=resume_file,
    )
    return SessionDetailResponse.model_validate(session)


@router.get("", response_model=SessionListResponse)
async def list_sessions(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> SessionListResponse:
    service = SessionService(db)
    sessions = await service.list_sessions(user_id=current_user["id"])
    return SessionListResponse(sessions=sessions, total=len(sessions))


@router.get("/{session_id}", response_model=SessionDetailResponse)
async def get_session(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> SessionDetailResponse:
    service = SessionService(db)
    session = await service.get_session(session_id, user_id=current_user["id"])
    return SessionDetailResponse.model_validate(session)


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> None:
    service = SessionService(db)
    await service.delete_session(session_id, user_id=current_user["id"])
```

---

## Quality Check Before Committing

Always run these before suggesting a commit:

```bash
cd backend
uv run ruff check app/
uv run ruff format --check app/
uv run mypy app/ ai_pipeline/ --ignore-missing-imports
uv run pytest tests/ -v
```

Fix all errors before committing.

---

## Commit Suggestions Per Layer

```
Models:       feat(db): add SQLAlchemy models for session, skill, question, answer, evaluation
Migration:    chore(db): create alembic migration for initial schema
Schemas:      feat(backend): add Pydantic schemas for all API request and response types
Repositories: feat(backend): implement base repository and domain-specific repository classes
Services:     feat(backend): implement session service with PDF parsing and skill persistence
Routers:      feat(backend): add FastAPI routers for sessions, skills, questions, answers
Auth:         feat(auth): add Supabase JWT verification dependency and auth router
```
