"""Private mutable drafts only. No submitted/clinical/training records."""
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Integer, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base


class AnnotationDraft(Base):
    __tablename__ = "annotation_drafts"
    __table_args__ = (
        ForeignKeyConstraint(["segmentation_result_id", "case_id"],
                             ["segmentation_results.id", "segmentation_results.case_id"], ondelete="RESTRICT"),
        CheckConstraint("revision > 0", name="ck_annotation_draft_revision"),
        CheckConstraint("status = 'unverified_server_draft'", name="ck_annotation_draft_status"),
        CheckConstraint("NOT clinical_gate_authorized AND NOT training_release_authorized", name="ck_annotation_draft_no_release"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id", ondelete="RESTRICT"))
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id", ondelete="RESTRICT"))
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    segmentation_result_id: Mapped[str] = mapped_column(String(36))
    source_volume_path: Mapped[str] = mapped_column(String(500))
    source_json: Mapped[dict] = mapped_column(JSON)
    geometry_sha256: Mapped[str] = mapped_column(String(64))
    segmentation_provenance: Mapped[dict] = mapped_column(JSON)
    document: Mapped[dict] = mapped_column(JSON)
    revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    status: Mapped[str] = mapped_column(String(40), default="unverified_server_draft", server_default="unverified_server_draft")
    clinical_gate_authorized: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    training_release_authorized: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
