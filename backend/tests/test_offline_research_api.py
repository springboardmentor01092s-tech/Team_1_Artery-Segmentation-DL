"""Stored synthetic NIfTI records only. Disposable schema; no inference/labels."""
from copy import deepcopy
from dataclasses import asdict
import base64
import hashlib
import json
from pathlib import Path
import builtins
import uuid
import subprocess
import sys

import pytest
pytest.importorskip('scipy')
from app.core.config import settings
from app.models import Case,SegmentationResult
from app.routers import offline_research as route
from app.services import offline_research as service
from scripts.research_candidate_profile import run_plan
from test_experimental_candidates import generate_frontend_fixture
from test_review_assignments import pair
from test_annotation_drafts import prepared


@pytest.fixture
def evidence(client,account,db,tmp_path,request):
    owner,headers=account('Clinician')
    native=getattr(request,'param',None)=='native'
    if native:
        folder=tmp_path/'native-synthetic'
        subprocess.run([sys.executable,'-B',str(Path(__file__).resolve().parents[1]/'scripts/demo_research_profile.py'),'--output',str(folder)],check=True,capture_output=True,timeout=90)
        exported=json.loads((folder/'profile-run/browser-evidence.json').read_text(encoding='utf-8'))
        plan=json.loads(exported['plan_json']);profile=exported['record']['profile'];profile['source']['mask_role']='model_prediction'
        bundle={'preview':profile,'ct_gzip_base64':base64.b64encode((folder/'synthetic-ct.nii.gz').read_bytes()).decode(),
            'mask_gzip_base64':base64.b64encode((folder/'synthetic-mask.nii.gz').read_bytes()).decode(),'input_branches':{'preview':plan['branches']}}
    else:bundle=generate_frontend_fixture('flipped');profile=bundle['preview']
    patient=client.post('/api/v1/patients',headers=headers,json={'patient_code':'OFFLINE-QA','display_name':'Synthetic offline verification'}).json()
    case=client.post('/api/v1/cases',headers=headers,json={'patient_id':patient['id'],'case_code':'OFFLINE-QA','modality':'CTA'}).json()
    ct=base64.b64decode(bundle['ct_gzip_base64']);mask=base64.b64decode(bundle['mask_gzip_base64'])
    assert client.post(f"/api/v1/cases/{case['id']}/volume",headers=headers,files={'file':('synthetic.nii.gz',ct)}).status_code==200
    stored=db.get(Case,case['id']);run_id=str(uuid.uuid4())
    profile['source']['parent_segmentation_result_id']=run_id
    directory=Path(settings.OUTPUT_DIR)/'segmentations'/run_id;directory.mkdir(parents=True)
    mp=directory/'prediction_mask.nii.gz';mp.write_bytes(mask)
    metadata={'source_sha256':hashlib.sha256(ct).hexdigest(),'shape':profile['geometry']['shape'],'affine':profile['geometry']['affine'],'xyzt_units':2,'architecture':'Synthetic software fixture; no model inference'}
    db.add(SegmentationResult(id=run_id,case_id=case['id'],created_by=owner.id,source_volume_path=stored.volume_path,metadata_json=metadata));db.commit()
    cp=Path(settings.UPLOAD_DIR)/stored.volume_path
    plan={'schema_version':'research-profile-plan/0.1','dataset_split':'synthetic','spatial_scope':'numerical_native_grid_only',
          'ct_sha256':metadata['source_sha256'],'mask_file_sha256':hashlib.sha256(mask).hexdigest(),'source':profile['source'],
          'geometry':profile['geometry'],'branches':bundle['input_branches']['preview'],'parameters':profile['parameters']}
    pp=tmp_path/'plan.json';pp.write_text(json.dumps(plan),encoding='utf-8')
    record=run_plan(cp,mp,pp,tmp_path/'producer')
    envelope={'schema_version':'offline-research-evidence/0.1','plan_json':pp.read_text(),'record':record}
    return {'url':f"/api/v1/cases/{case['id']}/segmentations/{run_id}/research-evidence/verify",'case_id':case['id'],'run_id':run_id,
            'headers':headers,'owner':owner,'ct_path':cp,'mask_path':mp,'metadata':metadata,'envelope':envelope,'tmp':tmp_path,'native':native}


def send(client,item,value=None,headers=None):
    raw=json.dumps(item['envelope'] if value is None else value)
    return client.post(item['url'],headers={**(headers or item['headers']),'Content-Type':'application/json'},content=raw)


@pytest.mark.parametrize('evidence',['small','native'],indirect=True)
def test_actual_files_verified_read_only_and_request_identity_bound(client,evidence,db):
    before=evidence['ct_path'].read_bytes(),evidence['mask_path'].read_bytes()
    response=send(client,evidence);assert response.status_code==200,response.text
    value=response.json();assert value['case_id']==evidence['case_id'] and value['segmentation_result_id']==evidence['run_id']
    assert value['profile']==evidence['envelope']['record']['profile']
    assert value['clinical_gate_authorized'] is value['training_release_authorized'] is False
    assert value['evidence_sha256']==hashlib.sha256(json.dumps(evidence['envelope']).encode()).hexdigest()
    assert response.headers['Cache-Control']=='no-store'
    assert before==(evidence['ct_path'].read_bytes(),evidence['mask_path'].read_bytes())
    assert not list((Path(settings.OUTPUT_DIR)/'.research-verification').iterdir())
    if evidence['native']:
        assert value['profile']['geometry']['shape']==[129,129,257]
        assert 129*129*257>4_000_000


def test_lightweight_identity_uses_actual_mask_bytes_and_stale_ct_refuses(client,evidence):
    url=evidence['url'].replace('/verify','/identity')
    response=client.get(url,headers=evidence['headers']);assert response.status_code==200 and response.headers['Cache-Control']=='no-store'
    assert response.json()['mask_file_sha256']==hashlib.sha256(evidence['mask_path'].read_bytes()).hexdigest()
    assert response.json()['clinical_gate_authorized'] is response.json()['training_release_authorized'] is False
    evidence['mask_path'].write_bytes(b'changed synthetic mask')
    assert client.get(url,headers=evidence['headers']).json()['mask_file_sha256']!=response.json()['mask_file_sha256']
    evidence['ct_path'].write_bytes(b'changed synthetic CT')
    assert client.get(url,headers=evidence['headers']).status_code==409


def test_identity_rechecks_metadata_after_concurrent_database_change(client,evidence,monkeypatch):
    from app.database.session import SessionLocal
    original=route._read_digest
    def changed(*args):
        digest=original(*args)
        with SessionLocal() as other:
            run=other.get(SegmentationResult,evidence['run_id']);run.metadata_json={**run.metadata_json,'threshold':.45};other.commit()
        return digest
    monkeypatch.setattr(route,'_read_digest',changed)
    assert client.get(evidence['url'].replace('/verify','/identity'),headers=evidence['headers']).status_code==409


@pytest.mark.parametrize('role',['Admin','Clinician','Researcher','DataScientist'])
def test_existing_case_readers_can_verify_without_new_authoring_permission(client,account,evidence,role):
    _,headers=account(role);assert send(client,evidence,headers=headers).status_code==200


@pytest.mark.parametrize('kind',['clinical','training','implementation','procedure','coordinate','parameter','branch','profile','mask_hash','source','incomplete'])
def test_forged_or_incomplete_evidence_never_accepted(client,evidence,kind):
    value=deepcopy(evidence['envelope'])
    if kind=='clinical':value['record']['clinical_gate_authorized']=True
    if kind=='training':value['record']['training_release_authorized']=True
    if kind=='implementation':value['record']['implementation_sha256']['sampler']='f'*64
    if kind=='procedure':value['record']['profile']['algorithm']['version']='forged'
    if kind=='coordinate':value['record']['profile']['candidates'][0]['sample_ijk'][0]+=1
    if kind=='parameter':value['record']['profile']['parameters_sha256']='f'*64
    if kind=='branch':value['record']['profile']['branch_geometry_sha256']='f'*64
    if kind=='profile':value['record']['profile']['branches'][0]['sections'][20]['diagnostic_area_mm2']+=1
    if kind=='mask_hash':value['record']['source_files']['mask_file_sha256']='f'*64
    if kind=='source':
        plan=json.loads(value['plan_json']);plan['source']['source_sha256']='f'*64;value['plan_json']=json.dumps(plan)
    if kind=='incomplete':value.pop('record')
    assert send(client,evidence,value).status_code in {409,422}


def test_unauthenticated_inactive_cross_case_and_stale_source_are_denied(client,account,evidence):
    assert client.post(evidence['url'],json=evidence['envelope']).status_code==401
    _,inactive=account('Researcher',active=False);assert send(client,evidence,headers=inactive).status_code==401
    wrong={**evidence,'url':evidence['url'].replace(f"/cases/{evidence['case_id']}/",'/cases/999999/')}
    assert send(client,wrong).status_code==404
    evidence['ct_path'].write_bytes(b'changed synthetic source')
    assert send(client,evidence).status_code==409


def test_mask_replacement_after_computation_is_detected(client,evidence,monkeypatch):
    original=route.verify
    def changed(*args):
        response=original(*args);evidence['mask_path'].write_bytes(b'changed synthetic mask');return response
    monkeypatch.setattr(route,'verify',changed)
    assert send(client,evidence).status_code==409


def test_session_revocation_during_computation_discards_response(client,evidence,db,monkeypatch):
    from app.database.session import SessionLocal
    from app.models import User
    original=route.verify
    def revoked(*args):
        response=original(*args)
        with SessionLocal() as other:
            actor=other.get(User,evidence['owner'].id);actor.token_version+=1;other.commit()
        return response
    monkeypatch.setattr(route,'verify',revoked);assert send(client,evidence).status_code==401


def test_runtime_missing_and_busy_fail_closed(client,evidence,monkeypatch):
    service.slot.acquire()
    try:assert send(client,evidence).status_code==503
    finally:service.slot.release()
    original=builtins.__import__
    def missing(name,*args,**kwargs):
        if name=='scripts.research_candidate_profile':raise ImportError('Synthetic missing runtime')
        return original(name,*args,**kwargs)
    monkeypatch.setattr(builtins,'__import__',missing);assert send(client,evidence).status_code==503


def test_duplicate_keys_and_streamed_oversize_refused_without_verification(client,evidence,monkeypatch):
    monkeypatch.setattr(route,'verify',lambda *args:pytest.fail('Verifier must not run on oversized input'))
    raw='{"schema_version":"offline-research-evidence/0.1","schema_version":"forged","record":{},"plan_json":"{}"}'
    # Parsing is within verify(), so exercise the parser independently here.
    with pytest.raises(Exception):service.parse_envelope(raw.encode())
    response=client.post(evidence['url'],headers={'Content-Type':'application/json'},content=iter([b'x'*65536 for _ in range(33)]))
    assert response.status_code==413


def test_blinded_reviewers_cannot_enter_offline_prediction_verification(client,pair):
    # The global reviewer allowlist must deny the new endpoint even with valid JWTs.
    response=client.post('/api/v1/review-studies',headers=pair['ah'],json=pair['body'])
    assert response.status_code==201,response.text
    url=f"/api/v1/cases/{pair['body']['case_id']}/segmentations/12345678-1234-4567-890a-123456789abc/research-evidence/verify"
    for reviewer in ['r1','r2']:
        from app.core.security import create_access_token
        actor=pair[reviewer]
        headers={'Authorization':'Bearer '+create_access_token(str(actor.id),actor.role,actor.token_version)}
        assert client.post(url,headers=headers,json={}).status_code==403
        assert client.get(url.replace('/verify','/identity'),headers=headers).status_code==403
