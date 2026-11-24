"""All credential evidence here is SYNTHETIC QA ONLY, never a real qualification."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from threading import Barrier, Event
from concurrent.futures import TimeoutError as FutureTimeout
from uuid import uuid4
import pytest
from sqlalchemy import select, update, delete, func, text
from sqlalchemy.exc import IntegrityError
from app.models.review_assignment import ReviewStudy
from app.models.review_adjudication import ReviewerCredential, AdjudicationAssignment, AdjudicationVersion
from app.services import review_adjudications as service, review_annotations
from test_annotation_drafts import prepared
from test_review_assignments import pair, assigned
from test_review_annotations import document, save, lesion


@pytest.fixture
def third(client, pair, account, db, request):
    ids = assigned(client, pair)
    for slot, headers in [('R1', pair['h1']), ('R2', pair['h2'])]:
        doc = document(pair, ids[slot])
        if getattr(request,'param',None)=='lesion_difference':
            row=lesion();row['draft_id']=str(uuid4());row['artery']='LAD' if slot=='R1' else 'RCA'
            doc.update(case_disposition='lesions_proposed',lesions=[row])
        result = client.put(f'/api/v1/review-assignments/{ids[slot]}/annotation-draft', headers=headers,
            json=dict(document=doc, expected_revision=0))
        assert result.status_code == 201, result.text
        result = client.post(f'/api/v1/review-assignments/{ids[slot]}/submit', headers=headers,
            json=dict(expected_revision=1, expected_document_sha256=result.json()['content_sha256'], acknowledge_unverified=True))
        assert result.status_code == 201, result.text
    user, headers = account('Clinician'); now = datetime.now(timezone.utc)
    credential = ReviewerCredential(id=str(uuid4()), reviewer_id=user.id, verified_by=pair['admin'].id,
        evidence_reference='SYNTHETIC QA ONLY - NOT A CLINICAL CREDENTIAL', evidence_sha256='a'*64,
        scope=service.SCOPE, verified_at=now-timedelta(days=1), valid_until=now+timedelta(days=1), revoked=False)
    db.add(credential); db.commit()
    study = db.scalar(select(ReviewStudy))
    body = dict(reviewer_id=user.id, credential_id=credential.id, expected_source_sha256=study.source_json['source_sha256'])
    return dict(user=user, headers=headers, credential=credential, study=study, body=body)


def allocate(client, pair, third):
    response = client.post(f"/api/v1/review-studies/{third['study'].id}/adjudicator", headers=pair['ah'], json=third['body'])
    assert response.status_code == 201, response.text
    return response.json()['id']


def blank(client, third, key):
    detail = client.get(f'/api/v1/review-adjudications/{key}', headers=third['headers'])
    assert detail.status_code == 200, detail.text
    data = detail.json()
    return dict(schema_version='review-adjudication/0.1', assignment_id=key, source_sha256=data['source']['source_sha256'],
        protocol_version=data['protocol_version'], r1_submission_sha256=data['parents'][0]['record_sha256'],
        r2_submission_sha256=data['parents'][1]['record_sha256'], outcome='unresolved',
        reason='Synthetic unassessed parent reviews; no clinical label', correspondences=[], resolutions=[],
        clinical_gate_authorized=False, training_release_authorized=False)


@pytest.mark.parametrize('invalid',['verifier_role','blank_evidence','whitespace_evidence','unicode_whitespace','malformed_hash'])
def test_ineligible_credentials_do_not_leak_through_lists_or_page_metadata(client,pair,third,db,account,invalid):
    key=allocate(client,pair,third)
    if invalid=='verifier_role':pair['admin'].role='Researcher'
    if invalid=='blank_evidence':third['credential'].evidence_reference='   '
    if invalid=='whitespace_evidence':third['credential'].evidence_reference='\t\n'
    if invalid=='unicode_whitespace':third['credential'].evidence_reference='\u2003\u00a0'
    if invalid=='malformed_hash':third['credential'].evidence_sha256='z'*64
    db.commit()
    response=client.get('/api/v1/review-adjudications?limit=1&offset=0',headers=third['headers'])
    assert response.status_code==200 and response.json()['items']==[] and response.json()['next_offset'] is None
    assert client.get(f'/api/v1/review-adjudications/{key}',headers=third['headers']).status_code==409
    _,admin=account('Admin')
    catalogue=client.get('/api/v1/review-adjudication-catalogue',headers=admin)
    assert catalogue.status_code==200 and catalogue.json()['credentials']==[]


def test_append_only_hash_chain_immutable_final_and_owner_isolation(client, pair, third, db):
    key = allocate(client, pair, third); doc = blank(client, third, key); url = f'/api/v1/review-adjudications/{key}'
    result = client.put(url+'/draft', headers=third['headers'], json=dict(document=doc, expected_revision=0))
    assert result.status_code == 200, result.text
    first = result.json(); assert review_annotations.content_hash(first['record']) == first['record_sha256']
    body = dict(expected_revision=1, expected_document_sha256=review_annotations.content_hash(doc), acknowledge_unverified=True)
    final = client.post(url+'/submit', headers=third['headers'], json=body)
    assert final.status_code == 201, final.text
    assert final.json()['record']['previous_sha256'] == first['record_sha256']
    assert final.json()['record']['status'] == 'adjudicated_unverified'
    assert final.json()['clinical_gate_authorized'] is final.json()['training_release_authorized'] is False
    repeated = client.post(url+'/submit', headers=third['headers'], json=body)
    assert repeated.status_code == 200 and repeated.json() == final.json()
    assert client.put(url+'/draft', headers=third['headers'], json=dict(document=doc, expected_revision=2)).status_code == 409
    detail = client.get(url, headers=third['headers']).json()
    assert len(detail['history']) == 2 and detail['history'][1]['final']
    coverage=detail['documentation_coverage']
    assert coverage['source_sha256']==detail['source']['source_sha256'] and coverage['protocol_version']==detail['protocol_version']
    assert [row['submission_sha256'] for row in coverage['readers']]==[row['record_sha256'] for row in detail['parents']]
    assert all(row['case_disposition']=='not_assessed' and row['recorded_lesion_rows']==row['landmark_fields']==0 for row in coverage['readers'])
    assert coverage['clinical_gate_authorized'] is coverage['training_release_authorized'] is False
    assert coverage['evidence_receipts_status']=='not_verified' and coverage['protocol_signoff_status']=='not_verified'
    for headers in [pair['ah'], pair['h1'], pair['h2']]:
        assert client.get(url, headers=headers).status_code in {403, 404}
        assert client.put(url+'/draft', headers=headers, json=dict(document=doc, expected_revision=2)).status_code in {403, 404}
    for cls in [AdjudicationAssignment, AdjudicationVersion]:
        with pytest.raises(IntegrityError): db.execute(delete(cls)); db.commit()
        db.rollback()


@pytest.mark.parametrize('kind', ['revoked', 'expired', 'wrong_scope', 'self_attested', 'missing', 'same_reader'])
def test_assignment_requires_actual_current_separate_credentials(client, pair, third, db, kind):
    body = deepcopy(third['body'])
    if kind == 'missing': body['credential_id'] = str(uuid4())
    elif kind == 'same_reader': body['reviewer_id'] = pair['r1'].id
    else:
        c = third['credential']
        if kind == 'revoked': c.revoked = True
        if kind == 'expired': c.valid_until = datetime.now(timezone.utc)-timedelta(seconds=1)
        if kind == 'wrong_scope': c.scope = 'unverified'
        if kind == 'self_attested': c.verified_by = third['user'].id
        db.commit()
    response = client.post(f"/api/v1/review-studies/{third['study'].id}/adjudicator", headers=pair['ah'], json=body)
    assert response.status_code == 409, response.text
    assert db.scalar(select(func.count()).select_from(AdjudicationAssignment)) == 0


@pytest.mark.parametrize('invalid',['revoked','evidence_hash'])
def test_credential_revocation_blocks_existing_reads_saves_and_source(client, pair, third, db, invalid):
    key = allocate(client, pair, third); doc = blank(client, third, key)
    db.execute(update(ReviewerCredential).values(**({'revoked':True} if invalid=='revoked' else {'evidence_sha256':'Z'*64}))); db.commit()
    url = f'/api/v1/review-adjudications/{key}'
    for suffix in ['', '/source']: assert client.get(url+suffix, headers=third['headers']).status_code == 409
    assert client.put(url+'/draft', headers=third['headers'], json=dict(document=doc, expected_revision=0)).status_code == 409
    assert client.get('/api/v1/cases', headers=third['headers']).status_code == 403


def test_third_reader_is_denied_every_legacy_api_and_independent_workflow(client, pair, third):
    from app.main import app
    import re
    allocate(client, pair, third); checked = set()
    for template, operations in app.openapi()['paths'].items():
        if not template.startswith('/api/v1/') or template.startswith(('/api/v1/auth/', '/api/v1/review-')): continue
        path = re.sub(r'\{[^}]+\}', str(uuid4()), template)
        for method in set(operations) & {'get', 'post', 'put', 'patch', 'delete'}:
            response = client.request(method, path, headers=third['headers'], json={} if method in {'post', 'put', 'patch'} else None)
            assert response.status_code == 403, (path, method, response.status_code)
            checked.add(template)
    assert len(checked) > 25
    assert client.get('/api/v1/review-assignments', headers=third['headers']).status_code == 403
    assert client.get('/api/v1/review-adjudication-catalogue', headers=pair['h1']).status_code == 403


@pytest.mark.parametrize('kind', ['source', 'parent_hash', 'foreign_lesion', 'release', 'false_agreement'])
def test_invalid_adjudication_does_not_create_final_record(client, pair, third, db, kind):
    key = allocate(client, pair, third); doc = blank(client, third, key); url = f'/api/v1/review-adjudications/{key}'
    if kind == 'source': doc['source_sha256'] = 'b'*64
    if kind == 'parent_hash': doc['r1_submission_sha256'] = 'c'*64
    if kind == 'release': doc['training_release_authorized'] = True
    if kind == 'foreign_lesion': doc['correspondences'] = [dict(id=str(uuid4()), r1_lesion_ids=[str(uuid4())], r2_lesion_ids=[], relation='only_r1', reason='Synthetic unknown lesion')]
    if kind == 'false_agreement': doc['outcome'] = 'agreement'
    saved = client.put(url+'/draft', headers=third['headers'], json=dict(document=doc, expected_revision=0))
    if kind == 'false_agreement':
        assert saved.status_code == 200
        response = client.post(url+'/submit', headers=third['headers'], json=dict(expected_revision=1,
            expected_document_sha256=review_annotations.content_hash(doc), acknowledge_unverified=True))
    else: response = saved
    assert response.status_code in {409, 422}, response.text
    assert db.scalar(select(func.count()).select_from(AdjudicationVersion).where(AdjudicationVersion.final)) == 0


def test_concurrent_adjudication_saves_use_distinct_pg_connections_and_one_wins(client, pair, third, db, monkeypatch):
    if db.bind.dialect.name != 'postgresql': pytest.skip('PostgreSQL concurrency')
    key = allocate(client, pair, third); doc = blank(client, third, key); barrier = Barrier(2, timeout=15); original = service.write_lock; pids = []
    def together(session, key):
        pids.append(session.scalar(text('SELECT pg_backend_pid()'))); barrier.wait(); return original(session, key)
    monkeypatch.setattr(service, 'write_lock', together)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: client.put(f'/api/v1/review-adjudications/{key}/draft', headers=third['headers'],
            json=dict(document=doc, expected_revision=0)), range(2)))
    assert sorted(r.status_code for r in responses) == [200, 409] and len(set(pids)) == 2
    assert db.scalar(select(func.count()).select_from(AdjudicationVersion)) == 1


def test_no_assignment_before_both_independent_submissions_are_frozen(client, pair, account, db):
    assigned(client, pair); user, _ = account('Clinician'); now = datetime.now(timezone.utc)
    c = ReviewerCredential(id=str(uuid4()), reviewer_id=user.id, verified_by=pair['admin'].id,
        evidence_reference='SYNTHETIC QA ONLY', evidence_sha256='a'*64, scope=service.SCOPE,
        verified_at=now-timedelta(days=1), valid_until=now+timedelta(days=1), revoked=False)
    db.add(c); db.commit(); study = db.scalar(select(ReviewStudy))
    response = client.post(f'/api/v1/review-studies/{study.id}/adjudicator', headers=pair['ah'], json=dict(
        reviewer_id=user.id, credential_id=c.id, expected_source_sha256=study.source_json['source_sha256']))
    assert response.status_code == 409 and 'Both independent' in response.json()['detail']
    assert db.scalar(select(AdjudicationAssignment)) is None


def test_changed_original_ct_blocks_adjudication_and_authentication_is_required(client, pair, third):
    key = allocate(client, pair, third); doc = blank(client, third, key); url = f'/api/v1/review-adjudications/{key}'
    assert client.get(url).status_code == 401
    pair['prepared']['path'].write_bytes(b'changed synthetic CT')
    response = client.get(url, headers=third['headers']); assert response.status_code == 200 and response.json()['source_current'] is False
    assert client.get(url+'/source', headers=third['headers']).status_code == 409
    assert client.put(url+'/draft', headers=third['headers'], json=dict(document=doc, expected_revision=0)).status_code == 409


def test_finalization_races_are_idempotent_and_do_not_duplicate_history(client, pair, third, db, monkeypatch):
    if db.bind.dialect.name != 'postgresql': pytest.skip('PostgreSQL concurrency')
    key = allocate(client, pair, third); doc = blank(client, third, key); url = f'/api/v1/review-adjudications/{key}'
    saved = client.put(url+'/draft', headers=third['headers'], json=dict(document=doc, expected_revision=0))
    assert saved.status_code == 200
    body = dict(expected_revision=1, expected_document_sha256=saved.json()['document_sha256'], acknowledge_unverified=True)
    original = service.write_lock; barrier = Barrier(2, timeout=15); pids = []
    def together(session, key):
        pids.append(session.scalar(text('SELECT pg_backend_pid()'))); barrier.wait(); return original(session, key)
    monkeypatch.setattr(service, 'write_lock', together)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: client.post(url+'/submit', headers=third['headers'], json=body), range(2)))
    assert sorted(r.status_code for r in responses) == [200, 201] and len(set(pids)) == 2
    assert responses[0].json() == responses[1].json()
    assert db.scalar(select(func.count()).select_from(AdjudicationVersion)) == 2


def test_hash_integrity_checks_reject_corrupted_snapshots():
    from types import SimpleNamespace
    from fastapi import HTTPException
    for payload in [None, {}, {'document':{}}, {'document':{}, 'training_release_authorized':True}]:
        with pytest.raises(HTTPException) as error:
            service.checked(SimpleNamespace(payload=payload, record_sha256='f'*64, document_sha256='d'*64))
        assert error.value.status_code == 409


@pytest.mark.parametrize('third',['lesion_difference'],indirect=True)
def test_all_actual_discrepant_fields_need_explicit_decisions(client,pair,third):
    key=allocate(client,pair,third);doc=blank(client,third,key);url=f'/api/v1/review-adjudications/{key}'
    parents=client.get(url,headers=third['headers']).json()['parents'];cid=str(uuid4())
    doc['correspondences']=[dict(id=cid,r1_lesion_ids=[parents[0]['submission']['document']['lesions'][0]['draft_id']],
        r2_lesion_ids=[parents[1]['submission']['document']['lesions'][0]['draft_id']],relation='matched',reason='Synthetic manual correspondence')]
    doc['resolutions']=[dict(correspondence_id=cid,field='lesion_presence',decision='agreement',reason='Both synthetic rows are present')]
    saved=client.put(url+'/draft',headers=third['headers'],json=dict(document=doc,expected_revision=0));assert saved.status_code==200
    body=dict(expected_revision=1,expected_document_sha256=saved.json()['document_sha256'],acknowledge_unverified=True)
    denied=client.post(url+'/submit',headers=third['headers'],json=body)
    assert denied.status_code==422 and 'artery_segment' in denied.json()['detail']
    doc['resolutions'].append(dict(correspondence_id=cid,field='artery_segment',decision='unresolved',reason='Artery entries differ; no expert ground truth'))
    saved=client.put(url+'/draft',headers=third['headers'],json=dict(document=doc,expected_revision=1));assert saved.status_code==200
    body.update(expected_revision=2,expected_document_sha256=saved.json()['document_sha256'])
    assert client.post(url+'/submit',headers=third['headers'],json=body).status_code==201


def test_history_is_bounded_without_losing_older_immutable_documents(client,pair,third,monkeypatch):
    key=allocate(client,pair,third);doc=blank(client,third,key);url=f'/api/v1/review-adjudications/{key}'
    monkeypatch.setattr(service,'HISTORY_LIMIT',2)
    records=[]
    for revision in range(3):
        doc['reason']=f'Synthetic revision {revision+1}'
        result=client.put(url+'/draft',headers=third['headers'],json=dict(document=doc,expected_revision=revision))
        assert result.status_code==200;records.append(result.json())
    detail=client.get(url,headers=third['headers']).json()
    assert detail['source_current'] is True
    assert detail['history_first_revision']==2 and detail['history_truncated'] is True
    assert [r['revision'] for r in detail['history']]==[2,3]
    assert detail['current']=={k:records[2][k] for k in ['record','record_sha256','document_sha256']}
    first=client.get(url+'/versions/1',headers=third['headers']);assert first.status_code==200 and first.json()==records[0]
    for headers in [pair['h1'],pair['h2'],pair['ah']]:
        assert client.get(url+'/versions/1',headers=headers).status_code in {403,404}


def test_detail_and_concurrent_save_return_one_consistent_history_snapshot(client,pair,third,monkeypatch,db):
    if db.bind.dialect.name!='postgresql':pytest.skip('PostgreSQL shared/exclusive row locks')
    key=allocate(client,pair,third);doc=blank(client,third,key);url=f'/api/v1/review-adjudications/{key}'
    assert client.put(url+'/draft',headers=third['headers'],json=dict(document=doc,expected_revision=0)).status_code==200
    entered,release=Event(),Event();original=service.latest
    def pause_read(session,key):
        if not entered.is_set():entered.set();assert release.wait(10)
        return original(session,key)
    monkeypatch.setattr(service,'latest',pause_read)
    with ThreadPoolExecutor(max_workers=2) as pool:
        reading=pool.submit(client.get,url,headers=third['headers'])
        assert entered.wait(10)
        writing=pool.submit(client.put,url+'/draft',headers=third['headers'],json=dict(document=doc,expected_revision=1))
        try:
            with pytest.raises(FutureTimeout):writing.result(timeout=.3)
        finally:release.set()
        read,write=reading.result(timeout=10),writing.result(timeout=10)
    assert read.status_code==write.status_code==200
    assert read.json()['current']['record']['revision']==read.json()['history'][-1]['revision']==1
    assert write.json()['record']['revision']==2


def test_expired_and_revoked_sessions_cannot_read_or_change_adjudication(client,pair,third,db):
    import jwt
    from app.core.config import settings
    from app.core.security import decode_access_token
    key=allocate(client,pair,third);doc=blank(client,third,key);url=f'/api/v1/review-adjudications/{key}'
    token=third['headers']['Authorization'].split(' ',1)[1];claims=decode_access_token(token)
    claims.update(iat=datetime.now(timezone.utc)-timedelta(hours=2),exp=datetime.now(timezone.utc)-timedelta(hours=1))
    expired={'Authorization':'Bearer '+jwt.encode(claims,settings.SECRET_KEY.get_secret_value(),algorithm=settings.ALGORITHM)}
    for headers in [expired]:
        assert client.get(url,headers=headers).status_code==401
        assert client.get(url+'/source',headers=headers).status_code==401
        assert client.put(url+'/draft',headers=headers,json=dict(document=doc,expected_revision=0)).status_code==401
    logged_out=client.post('/api/v1/auth/logout',headers=third['headers'])
    assert logged_out.status_code==204 and logged_out.content==b''
    assert client.get(url,headers=third['headers']).status_code==401
    assert db.scalar(select(AdjudicationVersion)) is None
