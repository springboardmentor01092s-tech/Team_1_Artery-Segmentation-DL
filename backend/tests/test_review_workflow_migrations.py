"""Populated 0012->0015 upgrade verification in disposable schema only."""
from alembic import command
from alembic.config import Config
from sqlalchemy import select, text
from app.database.session import engine
from app.models.review_annotation import ReviewAnnotationDraft, ReviewAnnotationVersion
from uuid import uuid4
from app.models.review_submission import IndependentReviewSubmission
from app.models.review_submission import ReviewSubmissionAmendment
from app.models.review_adjudication import ReviewerCredential
from app.schemas.review_assignment import AssignReaders
from app.schemas.review_annotation import SaveReviewAnnotation, SubmitReview
from app.schemas.review_amendment import CreateReviewAmendment
from app.services import review_assignments, review_annotations, review_submissions
from app.services import review_amendments
from test_annotation_drafts import prepared
from test_review_assignments import pair
from test_review_annotations import document


def test_populated_0012_0013_0014_0015_upgrades_preserve_originals_and_release_flags(pair, db):
    db.rollback(); cfg = Config('alembic.ini'); command.downgrade(cfg, '0012_ct_review_assignments')
    protected = ['users', 'patients', 'cases', 'segmentation_results', 'case_reviews', 'annotation_drafts']
    def snapshot():
        with engine.connect() as c:
            return {table: sorted((dict(r) for r in c.execute(text(f'SELECT * FROM {table}')).mappings()), key=repr) for table in protected}
    before = snapshot()
    command.upgrade(cfg, '0013_review_annotations'); assert snapshot() == before
    result = review_assignments.assign(db, pair['admin'], AssignReaders.model_validate(pair['body']))
    key = next(v['id'] for v in result['assignments'] if v['slot'] == 'R1')
    doc = document(pair, key)
    # Seed the historical 0013 layout directly. Current service code correctly
    # requires 0014's submission table and must not bypass missing schema.
    digest = review_annotations.content_hash(doc)
    db.add(ReviewAnnotationDraft(assignment_id=key,owner_id=pair['r1'].id,document=doc,revision=1,
        clinical_gate_authorized=False,training_release_authorized=False))
    db.add(ReviewAnnotationVersion(id=str(uuid4()),assignment_id=key,owner_id=pair['r1'].id,document=doc,revision=1,
        content_sha256=digest,clinical_gate_authorized=False,training_release_authorized=False))
    db.commit(); saved = {'content_sha256':digest}
    history = db.scalar(select(ReviewAnnotationVersion)); original = history.id, history.document, history.content_sha256
    db.commit(); command.upgrade(cfg, '0014_review_submissions')
    db.expire_all(); history = db.scalar(select(ReviewAnnotationVersion))
    assert (history.id, history.document, history.content_sha256) == original
    result, _ = review_submissions.submit(db, pair['r1'], key, SubmitReview(expected_revision=1,
        expected_document_sha256=saved['content_sha256'], acknowledge_unverified=True))
    db.commit(); command.upgrade(cfg, '0015_review_adjudication')
    db.expire_all(); frozen = db.scalar(select(IndependentReviewSubmission))
    assert frozen.payload == result['submission'] and frozen.record_sha256 == result['record_sha256']
    assert frozen.clinical_gate_authorized is frozen.training_release_authorized is False
    assert db.scalar(select(ReviewerCredential)) is None
    command.upgrade(cfg, '0016_review_amendments')
    db.expire_all(); frozen = db.scalar(select(IndependentReviewSubmission))
    amendment_document = dict(doc, case_unavailable_reason='Synthetic migration addendum; not clinical evidence.')
    amendment, created = review_amendments.append(db, pair['r1'], key, CreateReviewAmendment(
        document=amendment_document, reason='Synthetic migration preservation test.', expected_revision=0,
        expected_previous_sha256=None, expected_submission_sha256=frozen.record_sha256, acknowledge_unverified=True))
    assert created and amendment['amendment']['clinical_gate_authorized'] is False
    db.expire_all()
    assert db.get(IndependentReviewSubmission, frozen.id).record_sha256 == result['record_sha256']
    assert db.scalar(select(ReviewSubmissionAmendment)).record_sha256 == amendment['record_sha256']
    # Assignment audit rows are expected additions; original domain rows do not change.
    assert snapshot() == before
    with engine.connect() as c:
        assert c.scalar(text('SELECT version_num FROM alembic_version')) == '0016_review_amendments'
