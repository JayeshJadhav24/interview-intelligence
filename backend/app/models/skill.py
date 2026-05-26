import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Skill(Base):
    __tablename__ = "skills"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("interview_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    years_experience: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_bluff_risk: Mapped[bool] = mapped_column(default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    session: Mapped["InterviewSession"] = relationship("InterviewSession", back_populates="skills")  # type: ignore[name-defined]  # noqa: F821
    questions: Mapped[list["Question"]] = relationship("Question", back_populates="skill")  # type: ignore[name-defined]  # noqa: F821
