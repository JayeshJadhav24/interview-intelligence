import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Evaluation(Base):
    __tablename__ = "evaluations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("interview_sessions.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    overall_score: Mapped[float] = mapped_column(Float, nullable=False)
    technical_score: Mapped[float] = mapped_column(Float, nullable=False)
    communication_score: Mapped[float] = mapped_column(Float, nullable=False)
    recommendation: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # hire / no_hire / maybe
    strengths: Mapped[str] = mapped_column(Text, nullable=False)
    gaps: Mapped[str] = mapped_column(Text, nullable=False)
    bluff_summary: Mapped[str] = mapped_column(Text, nullable=False)
    full_report: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    session: Mapped["InterviewSession"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "InterviewSession", back_populates="evaluation"
    )
