"""Read-only verification of offline profiles against actual stored CT/mask bytes.

No inference, clinical provider, gate registration, submissions or persistence.
"""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
from threading import BoundedSemaphore

from fastapi import HTTPException

MAX_BYTES=2*1024*1024
slot=BoundedSemaphore(1)


def unique_object(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise ValueError('Duplicate JSON property')
        result[key]=value
    return result


def parse_envelope(raw):
    if not raw or len(raw)>MAX_BYTES:raise HTTPException(413,'Offline evidence must be nonempty and at most 2 MiB')
    try:
        value=json.loads(raw,object_pairs_hook=unique_object)
        if not isinstance(value,dict) or set(value)!={'schema_version','plan_json','record'} or value['schema_version']!='offline-research-evidence/0.1' or not isinstance(value['plan_json'],str):raise ValueError()
        plan=json.loads(value['plan_json'],object_pairs_hook=unique_object)
        # Reject NaN/infinity before any file or numerical operation.
        json.dumps(value,allow_nan=False);json.dumps(plan,allow_nan=False)
        return value,plan
    except (ValueError,TypeError,RecursionError):raise HTTPException(422,'Invalid or unsupported offline research evidence') from None


def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)


def verify(raw,ct_path,mask_path,case_id,result_id,metadata,scratch_root):
    envelope,plan=parse_envelope(raw)
    record=envelope['record']
    try:
        if record['schema_version']!='full-volume-research-profile/0.1' or record['clinical_gate_authorized'] is not False or record['training_release_authorized'] is not False:raise ValueError()
        source=plan['source'];g=plan['geometry']
        if source['mask_role']!='model_prediction' or source['parent_segmentation_result_id']!=result_id or type(source['target_label']) is not int or source['target_label']!=1:raise ValueError()
        if source['source_sha256']!=metadata['source_sha256'] or g['shape']!=metadata['shape'] or g['affine']!=metadata['affine']:raise ValueError()
        if record['profile']['algorithm']!={'id':'experimental-mask-profile','version':'0.1.0'}:raise ValueError()
    except (KeyError,TypeError,ValueError):raise HTTPException(409,'Offline evidence does not match this saved prediction/source') from None
    # Optional scientific dependencies stay outside ordinary FastAPI startup.
    try:
        from scripts.research_candidate_profile import run_plan,MAX_MASK_BYTES
    except (ImportError,OSError):raise HTTPException(503,'Offline research verification needs the optional SciPy research environment') from None
    if not slot.acquire(blocking=False):raise HTTPException(503,'Research verification is busy; retry after it completes',headers={'Retry-After':'30'})
    try:
        scratch_root=Path(scratch_root)
        if scratch_root.is_symlink() or scratch_root.is_junction():raise HTTPException(409,'Verification storage is unsafe')
        scratch_root.mkdir(mode=0o700,parents=True,exist_ok=True)
        if shutil.disk_usage(scratch_root).free<MAX_MASK_BYTES+16*1024*1024:raise HTTPException(503,'Insufficient verification scratch storage')
        with tempfile.TemporaryDirectory(prefix='offline-proof-',dir=scratch_root) as folder:
            folder=Path(folder)
            if folder.resolve().parent!=scratch_root.resolve():raise HTTPException(409,'Verification storage identity changed')
            plan_file=folder/'plan.json';plan_file.write_bytes(envelope['plan_json'].encode('utf-8'))
            try:computed=run_plan(ct_path,mask_path,plan_file,folder/'run')
            except (ValueError,OSError,KeyError,TypeError,OverflowError):raise HTTPException(409,'Offline evidence/source/geometry could not be verified') from None
            # This checks every field, implementation hash, environment version,
            # branch/parameter fingerprint, all samples/candidates and false flags.
            if canonical(computed)!=canonical(record):raise HTTPException(409,'Offline evidence was altered or uses an unsupported implementation/protocol')
        keys=['source_sha256','shape','affine','xyzt_units','checkpoint_sha256','threshold','architecture','model_name','model_version','recipe']
        return {'schema_version':'verified-offline-research/0.1','procedure_version':'0.1',
                'case_id':case_id,'segmentation_result_id':result_id,
                'evidence_sha256':hashlib.sha256(raw).hexdigest(),'verified_at':datetime.now(timezone.utc).isoformat(),
                'profile':computed['profile'],'source_files':computed['source_files'],
                'implementation_sha256':computed['implementation_sha256'],
                'segmentation':{'id':result_id,'case_id':case_id,'stale':False,'metadata':{k:metadata[k] for k in keys if k in metadata}},
                'verification_scope':'recomputed_against_current_stored_files_not_clinical_attestation',
                'clinical_gate_authorized':False,'training_release_authorized':False}
    finally:slot.release()
