"""Synthetic reader entries only, not expert labels. Disposable test schemas."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4
import pytest
from sqlalchemy import select,update,text,func
from sqlalchemy.exc import IntegrityError
from app.models.review_annotation import ReviewAnnotationDraft,ReviewAnnotationVersion
from app.services import review_annotations as service
from app.schemas.annotation_draft import POINT_FIELDS
from test_annotation_drafts import prepared,worksheet
from test_review_assignments import pair,assigned

def document(pair,assignment_id):
    source=deepcopy(pair['prepared']['source']);source.pop('segmentation_result_id')
    return dict(schema_version='independent-lesion-review/0.1',assignment_id=assignment_id,source=source,
      protocol_version=pair['body']['protocol_version'],status='unverified_draft',label_origin='manual_independent_reader_unverified',
      clinical_gate_authorized=False,training_release_authorized=False,reader_qualification_verified=False,reader_independence_verified=False,
      case_disposition='not_assessed',case_unavailable_reason='Synthetic unassessed software fixture',lesions=[])

def lesion():return {**worksheet(),'measurement_method':'','measurement_evidence':''}
def url(i):return f'/api/v1/review-assignments/{i}/annotation-draft'
def save(client,pair,i,doc,rev=0):return client.put(url(i),headers=pair['h1'],json={'document':doc,'expected_revision':rev})

def test_formal_manual_draft_nulls_private_history_and_local_schema(client,pair,db):
    ids=assigned(client,pair);i=ids['R1'];doc=document(pair,i)
    empty=client.get(url(i),headers=pair['h1']).json();assert empty['exists'] is False and empty['document'] is None
    doc['lesions']=[lesion()];doc['case_disposition']='lesions_proposed'
    response=save(client,pair,i,doc);assert response.status_code==201,response.text
    data=response.json();assert data['document']==doc and data['revision']==1
    assert data['content_sha256']==service.content_hash(doc)
    assert data['document']['lesions'][0]['minimum_lumen_diameter_mm'] is None
    for headers in [pair['h2'],pair['ah']]:
        assert client.get(url(i),headers=headers).status_code==404
        assert client.get(f'/api/v1/review-assignments/{i}/annotation-history',headers=headers).status_code==404
        assert client.put(url(i),headers=headers,json={'document':doc,'expected_revision':1}).status_code==404
    doc['lesions'][0]['notes']='explicitly revised synthetic text'
    assert save(client,pair,i,doc,1).json()['revision']==2
    assert save(client,pair,i,doc,1).status_code==409
    versions=db.scalars(select(ReviewAnnotationVersion).order_by(ReviewAnnotationVersion.revision)).all()
    assert len(versions)==2 and versions[0].document['lesions'][0]['notes']!='explicitly revised synthetic text'
    assert all(v.clinical_gate_authorized is v.training_release_authorized is False for v in versions)
    assert all(service.content_hash(v.document)==v.content_sha256 for v in versions)

@pytest.mark.parametrize('field',POINT_FIELDS)
def test_formal_landmarks_reject_outside_original_native_grid(client,pair,field):
    i=assigned(client,pair)['R1'];doc=document(pair,i);doc['lesions']=[lesion()];doc['lesions'][0][field]=[5,0,0]
    assert save(client,pair,i,doc).status_code==422

@pytest.mark.parametrize('kind',['source_hash','affine','assignment','protocol','clinical_release','training_release','qualification','unsupported_field','no_method','no_endpoints'])
def test_invalid_formal_metadata_is_not_persisted(client,pair,db,kind):
    i=assigned(client,pair)['R1'];doc=document(pair,i)
    if kind=='source_hash':doc['source']['source_sha256']='b'*64
    if kind=='affine':doc['source']['affine'][0][3]+=1
    if kind=='assignment':doc['assignment_id']=str(uuid4())
    if kind=='protocol':doc['protocol_version']='forged'
    if kind=='clinical_release':doc['clinical_gate_authorized']=True
    if kind=='training_release':doc['training_release_authorized']=True
    if kind=='qualification':doc['reader_qualification_verified']=True
    if kind=='unsupported_field':doc['model_confidence']=.9
    if kind in {'no_method','no_endpoints'}:
        doc['lesions']=[lesion()];row=doc['lesions'][0];row['minimum_lumen_diameter_mm']=0
        if kind=='no_method':row.update(minimum_caliper_start_ijk=[1,1,1],minimum_caliper_end_ijk=[1,1,1])
        else:row.update(measurement_method='synthetic manual test',measurement_evidence='No clinical meaning')
    assert save(client,pair,i,doc).status_code in {409,422}
    assert db.scalar(select(func.count()).select_from(ReviewAnnotationDraft))==0
    assert db.scalar(select(func.count()).select_from(ReviewAnnotationVersion))==0

def test_manual_zero_with_explicit_support_is_retained_without_computing_other_values(client,pair):
    i=assigned(client,pair)['R1'];doc=document(pair,i);doc['lesions']=[lesion()]
    row=doc['lesions'][0];row.update(minimum_lumen_diameter_mm=0,minimum_caliper_start_ijk=[1,1,1],minimum_caliper_end_ijk=[1,1,1],
        measurement_method='Synthetic software-only manual entry',measurement_evidence='Test values, not expert annotations')
    response=save(client,pair,i,doc);assert response.status_code==201,response.text
    actual=response.json()['document']['lesions'][0]
    assert actual['minimum_lumen_diameter_mm']==0 and actual['percentage_narrowing'] is None and actual['severity_category'] is None

def test_two_pg_connections_save_one_revision_and_history_is_immutable(client,pair,db,monkeypatch):
    if db.bind.dialect.name!='postgresql':pytest.skip('PostgreSQL concurrency')
    i=assigned(client,pair)['R1'];doc=document(pair,i);assert save(client,pair,i,doc).status_code==201
    from app.services import review_submissions
    original=review_submissions.write_lock;barrier=Barrier(2,timeout=15);pids=[]
    def both(session,key):
        pids.append(session.scalar(text('SELECT pg_backend_pid()')));barrier.wait();return original(session,key)
    monkeypatch.setattr(review_submissions,'write_lock',both)
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:save(client,pair,i,doc,1),range(2)))
    assert sorted(r.status_code for r in results)==[200,409] and len(set(pids))==2
    assert db.scalar(select(func.count()).select_from(ReviewAnnotationVersion))==2
    with pytest.raises(IntegrityError):db.execute(update(ReviewAnnotationVersion).values(content_sha256='f'*64));db.commit()
    db.rollback()

def test_changed_original_ct_blocks_formal_update(client,pair):
    i=assigned(client,pair)['R1'];doc=document(pair,i);assert save(client,pair,i,doc).status_code==201
    pair['prepared']['path'].write_bytes(b'changed software fixture')
    assert save(client,pair,i,doc,1).status_code==409
    old=client.get(url(i),headers=pair['h1']).json();assert old['source_current'] is False and old['document']==doc
