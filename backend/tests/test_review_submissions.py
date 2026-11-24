from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Barrier
import pytest
from sqlalchemy import select,update,delete,func,text
from sqlalchemy.exc import IntegrityError
from app.models.review_submission import IndependentReviewSubmission
from app.models.review_annotation import ReviewAnnotationDraft,ReviewAnnotationVersion
from app.services import review_submissions as service,review_annotations
from test_annotation_drafts import prepared
from test_review_assignments import pair,assigned
from test_review_annotations import document,save,url

def seeded(client,pair):
    i=assigned(client,pair)['R1'];doc=document(pair,i);response=save(client,pair,i,doc)
    assert response.status_code==201,response.text
    return i,doc,dict(expected_revision=1,expected_document_sha256=response.json()['content_sha256'],acknowledge_unverified=True)
def endpoint(i,suffix='submit'):return f'/api/v1/review-assignments/{i}/{suffix}'

def test_immutable_submission_hashes_identity_idempotency_and_no_release(client,pair,db):
    i,doc,body=seeded(client,pair)
    response=client.post(endpoint(i),headers=pair['h1'],json=body);assert response.status_code==201,response.text
    data=response.json();payload=data['submission']
    assert payload['document']==doc and payload['reviewer_id']==pair['r1'].id and payload['annotation_revision']==1
    assert payload['status']=='submitted_unverified_abstention' and payload['source_verified_at_submission'] is True
    assert review_annotations.content_hash(payload)==data['record_sha256']
    assert review_annotations.content_hash(payload['document'])==payload['document_sha256']
    assert payload['clinical_gate_authorized'] is payload['training_release_authorized'] is False
    repeated=client.post(endpoint(i),headers=pair['h1'],json=body)
    assert repeated.status_code==200 and repeated.json()==data
    assert db.scalar(select(func.count()).select_from(IndependentReviewSubmission))==1
    assert save(client,pair,i,doc,1).status_code==409
    current=client.get(url(i),headers=pair['h1']).json();assert current['submitted'] is True and current['revision']==1
    for headers in [pair['h2'],pair['ah']]:
        assert client.get(endpoint(i,'submission'),headers=headers).status_code==404
        assert client.post(endpoint(i),headers=headers,json=body).status_code==404
    for cls,values in [(IndependentReviewSubmission,{'record_sha256':'f'*64}),
                       (ReviewAnnotationDraft,{'revision':2}), (ReviewAnnotationVersion,{'content_sha256':'e'*64})]:
        with pytest.raises(IntegrityError):db.execute(update(cls).values(**values));db.commit()
        db.rollback()
    with pytest.raises(IntegrityError):db.execute(delete(IndependentReviewSubmission));db.commit()
    db.rollback()

@pytest.mark.parametrize('kind',['no_ack','stale_revision','wrong_hash','client_release','client_document'])
def test_submission_rejects_stale_or_untrusted_claims_without_record(client,pair,db,kind):
    i,doc,body=seeded(client,pair)
    if kind=='no_ack':body['acknowledge_unverified']=False
    if kind=='stale_revision':body['expected_revision']=2
    if kind=='wrong_hash':body['expected_document_sha256']='f'*64
    if kind=='client_release':body['clinical_gate_authorized']=True
    if kind=='client_document':body['document']=doc
    assert client.post(endpoint(i),headers=pair['h1'],json=body).status_code in {409,422}
    assert db.scalar(select(func.count()).select_from(IndependentReviewSubmission))==0
    assert db.get(ReviewAnnotationDraft,i).revision==1

def test_concurrent_submission_has_one_record_on_distinct_postgres_connections(client,pair,db,monkeypatch):
    if db.bind.dialect.name!='postgresql':pytest.skip('PostgreSQL concurrency')
    i,_,body=seeded(client,pair);barrier=Barrier(2,timeout=15);original=service.write_lock;pids=[]
    def together(session,key):pids.append(session.scalar(text('SELECT pg_backend_pid()')));barrier.wait();return original(session,key)
    monkeypatch.setattr(service,'write_lock',together)
    with ThreadPoolExecutor(max_workers=2) as pool:responses=list(pool.map(lambda _:client.post(endpoint(i),headers=pair['h1'],json=body),range(2)))
    assert sorted(r.status_code for r in responses)==[200,201] and len(set(pids))==2
    assert responses[0].json()==responses[1].json()
    assert db.scalar(select(func.count()).select_from(IndependentReviewSubmission))==1

def test_source_change_is_rejected_and_frozen_history_survives_later_change(client,pair):
    i,_,body=seeded(client,pair);original=pair['prepared']['path'].read_bytes()
    pair['prepared']['path'].write_bytes(b'changed synthetic source')
    assert client.post(endpoint(i),headers=pair['h1'],json=body).status_code==409
    pair['prepared']['path'].write_bytes(original)
    created=client.post(endpoint(i),headers=pair['h1'],json=body);assert created.status_code==201
    pair['prepared']['path'].write_bytes(b'later synthetic source change')
    old=client.get(endpoint(i,'submission'),headers=pair['h1']).json()
    assert old['source_current'] is False and old['submission']==created.json()['submission']
    assert old['record_sha256']==created.json()['record_sha256']


def test_save_and_submit_race_cannot_both_replace_the_same_revision(client,pair,db,monkeypatch):
    if db.bind.dialect.name!='postgresql':pytest.skip('PostgreSQL concurrency')
    i,doc,body=seeded(client,pair);original=service.write_lock;barrier=Barrier(2,timeout=15)
    def together(session,key):barrier.wait();return original(session,key)
    monkeypatch.setattr(service,'write_lock',together)
    with ThreadPoolExecutor(max_workers=2) as pool:
        saving=pool.submit(save,client,pair,i,doc,1)
        submitting=pool.submit(client.post,endpoint(i),headers=pair['h1'],json=body)
        a,b=saving.result(),submitting.result()
    assert (a.status_code,b.status_code) in {(409,201),(200,409)}
    db.expire_all();draft=db.get(ReviewAnnotationDraft,i)
    record=db.scalar(select(IndependentReviewSubmission))
    if record:assert draft.revision==1 and record.document_sha256==body['expected_document_sha256']
    else:assert draft.revision==2
