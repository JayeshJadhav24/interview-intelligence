import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class SessionStatus(str, enum.Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class InterviewSession(Base):
    __tablename__ = "interview_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    job_role: Mapped[str] = mapped_column(String(255), nullable=False)
    resume_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    jd_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[SessionStatus] = mapped_column(
        Enum(SessionStatus), default=SessionStatus.PENDING, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship("User", back_populates="sessions")  # type: ignore[name-defined]  # noqa: F821
    skills: Mapped[list["Skill"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Skill", back_populates="session", cascade="all, delete-orphan"
    )
    questions: Mapped[list["Question"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Question", back_populates="session", cascade="all, delete-orphan"
    )
    evaluation: Mapped["Evaluation | None"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Evaluation", back_populates="session", cascade="all, delete-orphan", uselist=False
    )
