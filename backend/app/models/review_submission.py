from datetime import datetime
from sqlalchemy import Boolean,CheckConstraint,DateTime,ForeignKey,ForeignKeyConstraint,Integer,JSON,String,UniqueConstraint,false,func
from sqlalchemy.orm import Mapped,mapped_column
from app.database.session import Base

class IndependentReviewSubmission(Base):
    __tablename__='independent_review_submissions'
    __table_args__=(UniqueConstraint('assignment_id',name='uq_independent_review_assignment'),
        ForeignKeyConstraint(['assignment_id','owner_id'],['review_assignments.id','review_assignments.reviewer_id'],ondelete='RESTRICT'),
        CheckConstraint('NOT clinical_gate_authorized AND NOT training_release_authorized',name='ck_independent_review_no_release'))
    id:Mapped[str]=mapped_column(String(36),primary_key=True)
    assignment_id:Mapped[str]=mapped_column(String(36))
    owner_id:Mapped[int]=mapped_column(ForeignKey('users.id',ondelete='RESTRICT'))
    version_id:Mapped[str]=mapped_column(ForeignKey('review_annotation_versions.id',ondelete='RESTRICT'))
    document_sha256:Mapped[str]=mapped_column(String(64))
    record_sha256:Mapped[str]=mapped_column(String(64))
    payload:Mapped[dict]=mapped_column(JSON)
    clinical_gate_authorized:Mapped[bool]=mapped_column(Boolean,server_default=false())
    training_release_authorized:Mapped[bool]=mapped_column(Boolean,server_default=false())
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())


class ReviewSubmissionAmendment(Base):
    """Append-only reviewer addenda; never rewrite a submitted parent review."""
    __tablename__='review_submission_amendments'
    __table_args__=(
        UniqueConstraint('assignment_id','revision',name='uq_review_amendment_revision'),
        ForeignKeyConstraint(['assignment_id','owner_id'],['review_assignments.id','review_assignments.reviewer_id'],ondelete='RESTRICT'),
        CheckConstraint('revision > 0',name='ck_review_amendment_revision'),
        CheckConstraint('NOT clinical_gate_authorized AND NOT training_release_authorized',name='ck_review_amendment_no_release'))
    id:Mapped[str]=mapped_column(String(36),primary_key=True)
    assignment_id:Mapped[str]=mapped_column(String(36),index=True)
    submission_id:Mapped[str]=mapped_column(ForeignKey('independent_review_submissions.id',ondelete='RESTRICT'))
    owner_id:Mapped[int]=mapped_column(ForeignKey('users.id',ondelete='RESTRICT'))
    revision:Mapped[int]=mapped_column(Integer)
    previous_id:Mapped[str|None]=mapped_column(ForeignKey('review_submission_amendments.id',ondelete='RESTRICT'))
    previous_sha256:Mapped[str|None]=mapped_column(String(64))
    parent_submission_sha256:Mapped[str]=mapped_column(String(64))
    document_sha256:Mapped[str]=mapped_column(String(64))
    record_sha256:Mapped[str]=mapped_column(String(64))
    payload:Mapped[dict]=mapped_column(JSON)
    clinical_gate_authorized:Mapped[bool]=mapped_column(Boolean,server_default=false())
    training_release_authorized:Mapped[bool]=mapped_column(Boolean,server_default=false())
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())
