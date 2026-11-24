"""Append-only research workflow decisions, bound to one saved model run."""
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, ForeignKeyConstraint, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base


class CaseReview(Base):
    __tablename__ = "case_reviews"
    __table_args__ = (
        ForeignKeyConstraint(["segmentation_result_id", "case_id"],
                             ["segmentation_results.id", "segmentation_results.case_id"], ondelete="CASCADE"),
        UniqueConstraint("segmentation_result_id", name="uq_case_review_run"),
        CheckConstraint("outcome IN ('accepted_for_research', 'changes_requested')", name="ck_case_review_outcome"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    segmentation_result_id: Mapped[str] = mapped_column(String(36))
    reviewer_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    reviewer_role: Mapped[str] = mapped_column(String(50))
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    outcome: Mapped[str] = mapped_column(String(40))
    note: Mapped[str | None] = mapped_column(Text(), nullable=True)
    source_sha256: Mapped[str] = mapped_column(String(64))
    checkpoint_sha256: Mapped[str] = mapped_column(String(64))
    mask_sha256: Mapped[str] = mapped_column(String(64))
    probabilities_sha256: Mapped[str] = mapped_column(String(64))
    threshold: Mapped[float] = mapped_column(Float)
