"""Restricted third-reader workflow. Credentials require separate human verification."""
from datetime import datetime
from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint, false, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database.session import Base


class ReviewerCredential(Base):
    __tablename__ = 'reviewer_credentials'
    __table_args__ = (CheckConstraint('valid_until > verified_at', name='ck_reader_credential_dates'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    reviewer_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='RESTRICT'), index=True)
    verified_by: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='RESTRICT'))
    evidence_reference: Mapped[str] = mapped_column(String(500))
    evidence_sha256: Mapped[str] = mapped_column(String(64))
    scope: Mapped[str] = mapped_column(String(128))
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())


class AdjudicationAssignment(Base):
    __tablename__ = 'adjudication_assignments'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    study_id: Mapped[str] = mapped_column(ForeignKey('review_studies.id', ondelete='RESTRICT'), unique=True)
    reviewer_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='RESTRICT'), index=True)
    coordinator_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='RESTRICT'))
    credential_id: Mapped[str] = mapped_column(ForeignKey('reviewer_credentials.id', ondelete='RESTRICT'))
    r1_submission_id: Mapped[str] = mapped_column(ForeignKey('independent_review_submissions.id', ondelete='RESTRICT'))
    r2_submission_id: Mapped[str] = mapped_column(ForeignKey('independent_review_submissions.id', ondelete='RESTRICT'))
    r1_sha256: Mapped[str] = mapped_column(String(64))
    r2_sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AdjudicationVersion(Base):
    __tablename__ = 'adjudication_versions'
    __table_args__ = (UniqueConstraint('assignment_id', 'revision', name='uq_adjudication_revision'),
                     CheckConstraint('revision > 0', name='ck_adjudication_revision'),
                     CheckConstraint('NOT clinical_gate_authorized AND NOT training_release_authorized', name='ck_adjudication_no_release'))
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    assignment_id: Mapped[str] = mapped_column(ForeignKey('adjudication_assignments.id', ondelete='RESTRICT'), index=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='RESTRICT'))
    revision: Mapped[int] = mapped_column(Integer)
    previous_id: Mapped[str | None] = mapped_column(ForeignKey('adjudication_versions.id', ondelete='RESTRICT'))
    previous_sha256: Mapped[str | None] = mapped_column(String(64))
    document_sha256: Mapped[str] = mapped_column(String(64))
    record_sha256: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON)
    final: Mapped[bool] = mapped_column(Boolean, default=False)
    clinical_gate_authorized: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    training_release_authorized: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
