"""CT-only assignment metadata and mutable private notes, not submissions."""
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Integer, JSON, String, Text, UniqueConstraint, false, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base


class ReviewStudy(Base):
    __tablename__ = "review_studies"
    __table_args__ = (CheckConstraint("NOT clinical_gate_authorized AND NOT training_release_authorized", name="ck_review_study_no_release"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id", ondelete="RESTRICT"), unique=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id", ondelete="RESTRICT"))
    coordinator_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    protocol_version: Mapped[str] = mapped_column(String(128))
    source_volume_path: Mapped[str] = mapped_column(String(500))
    source_json: Mapped[dict] = mapped_column(JSON)
    geometry_sha256: Mapped[str] = mapped_column(String(64))
    clinical_gate_authorized: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    training_release_authorized: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ReviewAssignment(Base):
    __tablename__ = "review_assignments"
    __table_args__ = (UniqueConstraint("study_id", "slot", name="uq_review_assignment_slot"),
                     UniqueConstraint("study_id", "reviewer_id", name="uq_review_assignment_distinct_reader"),
                     UniqueConstraint("id", "reviewer_id", name="uq_review_assignment_owner"),
                     CheckConstraint("slot IN ('R1','R2')", name="ck_review_assignment_slot"))
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    study_id: Mapped[str] = mapped_column(ForeignKey("review_studies.id", ondelete="RESTRICT"))
    reviewer_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    slot: Mapped[str] = mapped_column(String(2))


class ReviewNoteDraft(Base):
    __tablename__ = "review_note_drafts"
    __table_args__ = (ForeignKeyConstraint(["assignment_id", "owner_id"],
                         ["review_assignments.id", "review_assignments.reviewer_id"], ondelete="RESTRICT"),
                     CheckConstraint("revision > 0", name="ck_review_note_revision"),
                     CheckConstraint("NOT clinical_gate_authorized AND NOT training_release_authorized", name="ck_review_note_no_release"))
    assignment_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    notes: Mapped[str] = mapped_column(Text)
    revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    clinical_gate_authorized: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    training_release_authorized: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
