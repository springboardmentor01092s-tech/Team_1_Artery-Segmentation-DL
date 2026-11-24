"""Post-submission addenda are separate, owner-only, append-only records."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4
import pytest
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.exc import IntegrityError
from app.models.review_submission import IndependentReviewSubmission, ReviewSubmissionAmendment
from app.services import review_annotations, review_submissions
from test_review_submissions import seeded, endpoint
from test_review_assignments import pair
from test_annotation_drafts import prepared
from test_review_adjudications import third, allocate


def amendments_url(assignment_id):
    return endpoint(assignment_id, 'amendments')


def request_body(document, submission_hash, revision=0, previous_hash=None, **changes):
    return dict(document=document, reason='Correction/additional context recorded by the same reviewer; unverified.',
        expected_revision=revision, expected_previous_sha256=previous_hash,
        expected_submission_sha256=submission_hash, acknowledge_unverified=True, **changes)


def test_append_only_addendum_preserves_submission_and_is_private(client, pair, db):
    assignment_id, document, submit_body = seeded(client, pair)
    submitted = client.post(endpoint(assignment_id), headers=pair['h1'], json=submit_body)
    assert submitted.status_code == 201, submitted.text
    original = submitted.json()['submission']
    parent_hash = submitted.json()['record_sha256']
    changed = dict(document, case_unavailable_reason='Synthetic addendum detail; no clinical conclusion.')
    response = client.post(amendments_url(assignment_id), headers=pair['h1'],
        json=request_body(changed, parent_hash))
    assert response.status_code == 201, response.text
    entry = response.json()['amendment']
    assert entry['schema_version'] == 'review-submission-amendment/0.1'
    assert entry['status'] == 'unverified_addendum_original_submission_unchanged'
    assert entry['previous_id'] is None and entry['previous_sha256'] is None
    assert entry['parent_submission_sha256'] == parent_hash
    assert review_annotations.content_hash(entry) == response.json()['record_sha256']
    assert review_annotations.content_hash(entry['document']) == entry['document_sha256']
    assert response.json()['clinical_gate_authorized'] is response.json()['training_release_authorized'] is False
    original_after = client.get(endpoint(assignment_id, 'submission'), headers=pair['h1']).json()
    assert original_after['submission'] == original and original_after['record_sha256'] == parent_hash
    history = client.get(amendments_url(assignment_id), headers=pair['h1'])
    assert history.status_code == 200 and len(history.json()['items']) == 1
    assert history.json()['items'][0]['record_sha256'] == response.json()['record_sha256']
    for headers in (pair['h2'], pair['ah']):
        assert client.get(amendments_url(assignment_id), headers=headers).status_code == 404
        assert client.post(amendments_url(assignment_id), headers=headers,
            json=request_body(changed, parent_hash)).status_code == 404
    with pytest.raises(IntegrityError):
        db.execute(update(ReviewSubmissionAmendment).values(record_sha256='f'*64)); db.commit()
    db.rollback()
    with pytest.raises(IntegrityError):
        db.execute(delete(ReviewSubmissionAmendment)); db.commit()
    db.rollback()
    assert db.scalar(select(func.count()).select_from(IndependentReviewSubmission)) == 1


@pytest.mark.parametrize('kind', ['stale_revision', 'wrong_parent', 'forged_flag', 'invalid_document_source'])
def test_addendum_rejects_stale_or_untrusted_requests_without_mutation(client, pair, db, kind):
    assignment_id, document, submit_body = seeded(client, pair)
    submitted = client.post(endpoint(assignment_id), headers=pair['h1'], json=submit_body)
    assert submitted.status_code == 201, submitted.text
    original_hash = submitted.json()['record_sha256']
    changed = dict(document)
    revision=0; previous=None; parent=original_hash; extra={}
    if kind == 'stale_revision': revision=1; previous='a'*64
    elif kind == 'wrong_parent': parent='b'*64
    elif kind == 'forged_flag': extra['clinical_gate_authorized']=True
    elif kind == 'invalid_document_source':
        changed['source']=dict(document['source'], source_sha256='c'*64)
    before=db.scalar(select(func.count()).select_from(ReviewSubmissionAmendment))
    response=client.post(amendments_url(assignment_id),headers=pair['h1'],
        json=request_body(changed,parent,revision,previous,**extra))
    assert response.status_code in {409,422}
    assert db.scalar(select(func.count()).select_from(ReviewSubmissionAmendment)) == before
    assert client.get(endpoint(assignment_id,'submission'),headers=pair['h1']).json()['record_sha256']==original_hash


def test_two_pg_connections_cannot_append_same_amendment_revision(client,pair,db,monkeypatch):
    if db.bind.dialect.name!='postgresql':pytest.skip('PostgreSQL concurrency')
    assignment_id, document, submit_body=seeded(client,pair)
    submitted=client.post(endpoint(assignment_id),headers=pair['h1'],json=submit_body)
    assert submitted.status_code==201,submitted.text
    parent_hash=submitted.json()['record_sha256']
    changed=dict(document,case_unavailable_reason='Concurrent synthetic amendment attempt.')
    body=request_body(changed,parent_hash)
    barrier=Barrier(2,timeout=15); original=review_submissions.write_lock; pids=[]
    def synchronized(session,key):
        pids.append(session.scalar(text('SELECT pg_backend_pid()')));barrier.wait();return original(session,key)
    monkeypatch.setattr(review_submissions,'write_lock',synchronized)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:client.post(amendments_url(assignment_id),headers=pair['h1'],json=body),range(2)))
    assert sorted(r.status_code for r in results)==[201,409]
    assert len(set(pids))==2
    db.expire_all()
    rows=db.scalars(select(ReviewSubmissionAmendment).where(ReviewSubmissionAmendment.assignment_id==assignment_id)).all()
    assert len(rows)==1 and rows[0].revision==1


def test_amendment_and_third_reader_assignment_are_mutually_exclusive(client,pair,third,db):
    # The fixture has two frozen submissions but no adjudicator yet. Add an R1
    # addendum, then prove the coordinator cannot bind R3 to only the old pair.
    from app.models.review_assignment import ReviewAssignment
    r1=db.scalar(select(ReviewAssignment).where(ReviewAssignment.study_id==third['study'].id,ReviewAssignment.slot=='R1'))
    parent=db.scalar(select(IndependentReviewSubmission).where(IndependentReviewSubmission.assignment_id==r1.id))
    base=parent.payload['document'];changed=dict(base,case_unavailable_reason='Synthetic addendum precludes unbound adjudication.')
    result=client.post(amendments_url(r1.id),headers=pair['h1'],json=request_body(changed,parent.record_sha256))
    assert result.status_code==201,result.text
    response=client.post(f"/api/v1/review-studies/{third['study'].id}/adjudicator",headers=pair['ah'],json=third['body'])
    assert response.status_code==409
