from datetime import datetime
from sqlalchemy import Boolean,CheckConstraint,DateTime,ForeignKey,ForeignKeyConstraint,Integer,JSON,String,UniqueConstraint,false,func
from sqlalchemy.orm import Mapped,mapped_column
from app.database.session import Base

class ReviewAnnotationDraft(Base):
    __tablename__='review_annotation_drafts'
    __table_args__=(ForeignKeyConstraint(['assignment_id','owner_id'],['review_assignments.id','review_assignments.reviewer_id'],ondelete='RESTRICT'),
                   CheckConstraint('revision>0',name='ck_review_annotation_revision'),
                   CheckConstraint('NOT clinical_gate_authorized AND NOT training_release_authorized',name='ck_review_annotation_no_release'))
    assignment_id:Mapped[str]=mapped_column(String(36),primary_key=True)
    owner_id:Mapped[int]=mapped_column(ForeignKey('users.id',ondelete='RESTRICT'))
    document:Mapped[dict]=mapped_column(JSON)
    revision:Mapped[int]=mapped_column(Integer)
    clinical_gate_authorized:Mapped[bool]=mapped_column(Boolean,server_default=false())
    training_release_authorized:Mapped[bool]=mapped_column(Boolean,server_default=false())
    updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())

class ReviewAnnotationVersion(Base):
    __tablename__='review_annotation_versions'
    __table_args__=(UniqueConstraint('assignment_id','revision',name='uq_review_annotation_version'),
                   ForeignKeyConstraint(['assignment_id','owner_id'],['review_assignments.id','review_assignments.reviewer_id'],ondelete='RESTRICT'),
                   CheckConstraint('revision>0',name='ck_review_annotation_version_revision'),
                   CheckConstraint('NOT clinical_gate_authorized AND NOT training_release_authorized',name='ck_review_annotation_version_no_release'))
    id:Mapped[str]=mapped_column(String(36),primary_key=True)
    assignment_id:Mapped[str]=mapped_column(String(36),index=True)
    owner_id:Mapped[int]=mapped_column(ForeignKey('users.id',ondelete='RESTRICT'))
    revision:Mapped[int]=mapped_column(Integer)
    document:Mapped[dict]=mapped_column(JSON)
    content_sha256:Mapped[str]=mapped_column(String(64))
    clinical_gate_authorized:Mapped[bool]=mapped_column(Boolean,server_default=false())
    training_release_authorized:Mapped[bool]=mapped_column(Boolean,server_default=false())
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())
