import hashlib
import json
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import select,update,func
from app.models.review_annotation import ReviewAnnotationDraft,ReviewAnnotationVersion
from app.models.review_submission import IndependentReviewSubmission
from app.schemas.review_annotation import ReviewAnnotation
from app.services import review_assignments as assignments
from app.services.source_fingerprint import file_version
from app.services.audit import record_event

def content_hash(document):
    return hashlib.sha256(json.dumps(document,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')).hexdigest()

def validate_binding(document,row,study):
    value=ReviewAnnotation.model_validate(document)
    if value.assignment_id!=row.id or value.protocol_version!=study.protocol_version or value.source.model_dump()!=study.source_json:
        raise HTTPException(409,'Annotation does not match the assigned original CT and protocol')
    return value.model_dump(mode='json')

def for_save(db,assignment_id):return db.get(ReviewAnnotationDraft,assignment_id)

def envelope(row,study,draft,current=True,reason=None,submitted=False):
    document=validate_binding(draft.document,row,study) if draft else None
    return dict(assignment_id=row.id,owner_id=row.reviewer_id,case_id=study.case_id,protocol_version=study.protocol_version,
        source=study.source_json,geometry_identity={'version':'ct-geometry/1.0','sha256':study.geometry_sha256},
        revision=draft.revision if draft else 0,exists=draft is not None,document=document,
        content_sha256=content_hash(document) if document else None,status='unverified_draft',
        source_current=current,source_unavailable_reason=reason,submitted=submitted,**assignments.no_release())

def read(db,actor,assignment_id):
    row,study=assignments.own_assignment(db,actor,assignment_id)
    current,reason=True,None
    try:assignments.verify_assigned_source(db,study)
    except HTTPException:current,reason=False,'Bound original CT is unavailable or changed.'
    submitted=db.scalar(select(IndependentReviewSubmission.id).where(IndependentReviewSubmission.assignment_id==row.id)) is not None
    result=envelope(row,study,db.get(ReviewAnnotationDraft,row.id),current,reason,submitted);db.commit();return result

def save(db,actor,assignment_id,data):
    row,study=assignments.own_assignment(db,actor,assignment_id)
    from app.services.review_submissions import write_lock
    write_lock(db,row.id)
    if db.scalar(select(IndependentReviewSubmission.id).where(IndependentReviewSubmission.assignment_id==row.id)):
        raise HTTPException(409,'Submitted annotations are immutable; a separate versioned amendment process is required')
    _,_,path,version,_=assignments.verify_assigned_source(db,study)
    document=validate_binding(data.document.model_dump(mode='json'),row,study)
    draft=for_save(db,row.id)
    if draft is None and data.expected_revision==0:
        draft=ReviewAnnotationDraft(assignment_id=row.id,owner_id=actor.id,document=document,revision=1,
            clinical_gate_authorized=False,training_release_authorized=False)
        db.add(draft);db.flush();created=True
    else:
        created=False
        if draft is None or data.expected_revision<1:raise HTTPException(409,'Annotation revision conflict; reload before saving')
        changed=db.execute(update(ReviewAnnotationDraft).where(ReviewAnnotationDraft.assignment_id==row.id,
            ReviewAnnotationDraft.owner_id==actor.id,ReviewAnnotationDraft.revision==data.expected_revision)
            .values(document=document,revision=data.expected_revision+1,updated_at=func.now()).execution_options(synchronize_session=False))
        if changed.rowcount!=1:raise HTTPException(409,'Annotation revision conflict; reload before saving')
        db.refresh(draft)
    db.add(ReviewAnnotationVersion(id=str(uuid4()),assignment_id=row.id,owner_id=actor.id,revision=draft.revision,
        document=document,content_sha256=content_hash(document),clinical_gate_authorized=False,training_release_authorized=False))
    db.flush()
    if file_version(path)!=version:raise HTTPException(409,'CT source changed during annotation save')
    result=envelope(row,study,draft);record_event(db,'review.annotation_saved',actor.id,study.case_id);db.commit()
    return result,created

def history(db,actor,assignment_id,limit=20,offset=0):
    row,study=assignments.own_assignment(db,actor,assignment_id)
    rows=db.scalars(select(ReviewAnnotationVersion).where(ReviewAnnotationVersion.assignment_id==row.id,
        ReviewAnnotationVersion.owner_id==actor.id).order_by(ReviewAnnotationVersion.revision.desc()).offset(offset).limit(limit+1)).all()
    for version in rows:
        validate_binding(version.document,row,study)
        if content_hash(version.document)!=version.content_sha256:raise HTTPException(409,'Annotation history integrity mismatch')
    result=dict(items=[dict(id=v.id,revision=v.revision,content_sha256=v.content_sha256,created_at=v.created_at) for v in rows[:limit]],
        next_offset=offset+limit if len(rows)>limit and offset+limit<=1_000_000 else None,**assignments.no_release())
    db.commit();return result
