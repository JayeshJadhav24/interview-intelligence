import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Answer(Base):
    __tablename__ = "answers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("questions.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_bluff_detected: Mapped[bool] = mapped_column(default=False, nullable=False)
    follow_up_generated: Mapped[bool] = mapped_column(default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    question: Mapped["Question"] = relationship("Question", back_populates="answer")  # type: ignore[name-defined]  # noqa: F821
