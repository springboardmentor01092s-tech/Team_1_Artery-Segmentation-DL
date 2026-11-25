"""Explicit authenticated file-bound research verification; never inference."""
from pathlib import Path
from fastapi import APIRouter,HTTPException,Request,Response
from starlette.concurrency import run_in_threadpool
from app.core.config import settings
from app.routers.cases import AuthenticatedCaseReader,DatabaseSession,UPLOAD_DIR,VOLUME_DIR
from app.routers.segmentation import current_result,result_directory
from app.services.offline_research import verify,canonical
from app.services.source_fingerprint import file_version,_read_digest

router=APIRouter(prefix='/cases',tags=['Offline research evidence'])


@router.get('/{case_id}/segmentations/{result_id}/research-evidence/identity')
def source_identity(case_id:int,result_id:str,response:Response,current_user:AuthenticatedCaseReader,db:DatabaseSession):
    """File freshness only; no profile claim, inference or persistent receipt."""
    _,result=current_result(db,case_id,result_id)
    actor_snapshot=(current_user.token_version,current_user.role);metadata_snapshot=canonical(result.metadata_json)
    folder=result_directory(result_id);mask=folder/'prediction_mask.nii.gz'
    try:
        if folder.name!=result_id or folder.is_symlink() or folder.is_junction() or mask.is_symlink() or mask.is_junction() or mask.resolve().parent!=folder.resolve():raise OSError()
        version=file_version(mask)
        if version[2]>2*1024**3:raise OSError()
        digest=_read_digest(str(mask),version)
    except OSError:raise HTTPException(409,'Stored mask identity could not be verified') from None
    db.expire_all()
    _,fresh=current_result(db,case_id,result_id)
    db.refresh(current_user)
    if not current_user.is_active or (current_user.token_version,current_user.role)!=actor_snapshot:raise HTTPException(401,'Session changed during identity verification')
    if canonical(fresh.metadata_json)!=metadata_snapshot:raise HTTPException(409,'Saved segmentation changed during identity verification')
    keys=['source_sha256','shape','affine','xyzt_units','checkpoint_sha256','threshold','architecture','model_name','model_version','recipe']
    response.headers['Cache-Control']='no-store'
    return {'schema_version':'offline-research-source/0.1','case_id':case_id,'segmentation_result_id':result_id,
        'mask_file_sha256':digest,'segmentation':{'id':result_id,'case_id':case_id,'stale':False,'metadata':{k:fresh.metadata_json[k] for k in keys if k in fresh.metadata_json}},
        'clinical_gate_authorized':False,'training_release_authorized':False}


@router.post('/{case_id}/segmentations/{result_id}/research-evidence/verify')
async def verify_evidence(case_id:int,result_id:str,request:Request,response:Response,current_user:AuthenticatedCaseReader,db:DatabaseSession):
    if request.headers.get('content-type','').split(';')[0].strip()!='application/json':raise HTTPException(415,'JSON research evidence required')
    raw=await request.body()
    response.headers['Cache-Control']='no-store'
    return await run_in_threadpool(verify_request,case_id,result_id,raw,current_user,db)


def verify_request(case_id,result_id,raw,current_user,db):
    case,result=current_result(db,case_id,result_id)
    source=UPLOAD_DIR/case.volume_path;directory=result_directory(result_id);mask=directory/'prediction_mask.nii.gz'
    if source.is_symlink() or source.is_junction() or source.resolve().parent!=VOLUME_DIR.resolve() or mask.is_symlink() or directory.is_symlink() or directory.is_junction() or directory.name!=result_id:
        raise HTTPException(409,'Stored research source identity is unsafe')
    identity=canonical(result.metadata_json);metadata=dict(result.metadata_json)
    actor_id,version,role=current_user.id,current_user.token_version,current_user.role
    db.rollback()  # No long transaction during bounded file verification.
    response=verify(raw,source,mask,case_id,result_id,metadata,Path(settings.OUTPUT_DIR)/'.research-verification')
    db.expire_all()
    from app.models import User
    actor=db.get(User,actor_id)
    if actor is None or not actor.is_active or actor.token_version!=version or actor.role!=role:raise HTTPException(401,'Session changed during verification')
    _,fresh=current_result(db,case_id,result_id)
    if canonical(fresh.metadata_json)!=identity:raise HTTPException(409,'Saved segmentation changed during verification')
    try:
        if mask.is_symlink() or _read_digest(str(mask.resolve()),file_version(mask))!=response['source_files']['mask_file_sha256']:raise OSError()
    except OSError:raise HTTPException(409,'Stored mask changed during verification') from None
    return response
