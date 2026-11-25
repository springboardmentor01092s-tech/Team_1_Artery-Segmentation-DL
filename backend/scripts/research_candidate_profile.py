"""Explicit offline native-grid profile run; no DB, inference or clinical release.

Use a private external output directory. Only supplied Training/synthetic sources
and explicitly source-bound ordered branches are accepted. No dataset discovery.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import sys
import platform
import re
from time import monotonic

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import nibabel as nib
import numpy as np
import scipy
from app.schemas.stenosis import VolumeGeometry
from app.services.experimental_candidates import CandidateInputError, ResearchParameters
from app.services.tiled_candidate_profile import extract_tiled_candidates, MAX_FULL_VOXELS

MAX_FILE_BYTES=2*1024**3
MAX_MASK_BYTES=MAX_FULL_VOXELS+2*1024*1024


def failure_code(error):
    if isinstance(error,CandidateInputError) and re.fullmatch(r'[a-z0-9_]{1,100}',str(error)):return str(error)
    if isinstance(error,FileExistsError):return 'output_collision'
    if isinstance(error,json.JSONDecodeError):return 'invalid_plan_json'
    if isinstance(error,OSError):return 'source_io_failure'
    return 'invalid_input_or_profile_failure'


def sha(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size>MAX_FILE_BYTES:
        raise CandidateInputError('unsafe_or_oversized_source_file')
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):digest.update(chunk)
    return digest.hexdigest()


def write_new(path,value):
    data=(json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
    if len(data)>2*1024*1024:raise CandidateInputError('output_document_budget')
    with path.open('xb') as stream:stream.write(data)
    return hashlib.sha256(data).hexdigest()


def run_plan(ct_path,mask_path,plan_path,output):
    start=monotonic();ct_path=Path(ct_path);mask_path=Path(mask_path);plan_path=Path(plan_path);output=Path(output)
    # No writes into either a source directory or the repository/build context.
    repo=Path(__file__).resolve().parents[2]
    if output.is_symlink() or output.resolve().is_relative_to(repo):raise CandidateInputError('external_output_required')
    if plan_path.is_symlink() or not plan_path.is_file() or plan_path.stat().st_size>2*1024*1024:
        raise CandidateInputError('plan_document_budget')
    raw=plan_path.read_bytes();plan=json.loads(raw)
    required={'schema_version','dataset_split','spatial_scope','ct_sha256','mask_file_sha256','source','geometry','branches','parameters'}
    if not isinstance(plan,dict) or set(plan)!=required or plan['schema_version']!='research-profile-plan/0.1':
        raise CandidateInputError('explicit_profile_plan_required')
    if plan['dataset_split'] not in {'Training','synthetic'} or plan['spatial_scope']!='numerical_native_grid_only':
        raise CandidateInputError('training_or_synthetic_numerical_scope_required')
    if any(not p.name.lower().endswith(('.nii','.nii.gz')) for p in [ct_path,mask_path]):
        raise CandidateInputError('single_file_nifti_sources_required')
    ct_hash,mask_hash=sha(ct_path),sha(mask_path)
    if ct_hash!=plan['ct_sha256'] or ct_hash!=plan['source']['source_sha256'] or mask_hash!=plan['mask_file_sha256']:
        raise CandidateInputError('source_file_checksum_mismatch')
    geometry=VolumeGeometry.model_validate(plan['geometry']);parameters=ResearchParameters(**plan['parameters'])
    ct=nib.load(str(ct_path),mmap='r')
    if len(ct.shape)!=3 or tuple(ct.shape)!=geometry.shape or ct.header.get_xyzt_units()[0]!='mm' or not (ct.header['sform_code']>0 or ct.header['qform_code']>0):
        raise CandidateInputError('original_coded_ct_mm_geometry_required')
    if not np.array_equal(ct.affine,np.asarray(geometry.affine)):raise CandidateInputError('ct_plan_geometry_mismatch')
    output.mkdir(mode=0o700,parents=False,exist_ok=False)
    scratch=output/'mask-snapshot.nii';mapped=None
    try:
        # Bounded gzip expansion; never allocate a decompressed full-volume array.
        opener=gzip.open if mask_path.name.lower().endswith('.nii.gz') else open
        with opener(mask_path,'rb') as source,scratch.open('xb') as target:
            total=0
            for chunk in iter(lambda:source.read(1024*1024),b''):
                total+=len(chunk)
                if total>MAX_MASK_BYTES:raise CandidateInputError('decompressed_mask_budget')
                target.write(chunk)
        image=nib.load(str(scratch),mmap='r')
        if type(image) is not nib.Nifti1Image or image.get_data_dtype()!=np.dtype('uint8') or len(image.shape)!=3:
            raise CandidateInputError('unscaled_uint8_nifti1_mask_required')
        if image.dataobj.slope!=1 or image.dataobj.inter!=0 or image.header.get_xyzt_units()[0]!='mm':
            raise CandidateInputError('mask_scale_or_units_unresolved')
        if not (image.header['sform_code']>0 or image.header['qform_code']>0) or tuple(image.shape)!=geometry.shape or not np.array_equal(image.affine,ct.affine) or not np.array_equal(image.header.get_zooms()[:3],ct.header.get_zooms()[:3]):
            raise CandidateInputError('mask_ct_numerical_geometry_mismatch')
        offset=image.dataobj.offset
        if offset<352 or offset>2*1024*1024 or offset+int(np.prod(image.shape))>total:raise CandidateInputError('invalid_mask_payload_extent')
        mapped=np.memmap(scratch,mode='r',dtype=np.uint8,offset=offset,shape=image.shape,order='F')
        profile=extract_tiled_candidates(mapped,geometry,ct.header.get_zooms()[:3],plan['source'],plan['branches'],parameters)
        mapped._mmap.close();mapped=None
        if sha(ct_path)!=ct_hash or sha(mask_path)!=mask_hash or hashlib.sha256(plan_path.read_bytes()).hexdigest()!=hashlib.sha256(raw).hexdigest():
            raise CandidateInputError('source_changed_during_analysis')
        record={'schema_version':'full-volume-research-profile/0.1','profile':profile,
                'source_files':{'ct_sha256':ct_hash,'mask_file_sha256':mask_hash,'plan_sha256':hashlib.sha256(raw).hexdigest()},
                'storage_method':'bounded_native_uint8_slab_scan_and_mapped_plane_gather/0.1',
                'scope':'Supplied ordered branches only; whole mask connectivity/hash checked. No registration or clinical validity established.',
                'dataset_split':plan['dataset_split'],'clinical_gate_authorized':False,'training_release_authorized':False}
        record['split_verification_status']='operator_declared; source hashes verified, dataset membership/licensing not attested by this tool'
        backend=Path(__file__).resolve().parents[1]
        implementation={'sampler':backend/'app/services/experimental_candidates.py',
                        'storage':backend/'app/services/tiled_candidate_profile.py','orchestrator':Path(__file__).resolve()}
        record['implementation_sha256']={key:hashlib.sha256(path.read_bytes()).hexdigest() for key,path in implementation.items()}
        record['environment']={'python':platform.python_version(),'numpy':np.__version__,'scipy':scipy.__version__,'nibabel':nib.__version__}
        checksum=write_new(output/'profile.json',record)
        write_new(output/'RUN.json',{'status':'COMPLETE','profile_sha256':checksum,'elapsed_seconds':monotonic()-start,
                  'voxels':int(np.prod(geometry.shape)),'original_sources_unchanged':True,'full_volume_array_loaded':False,
                  'clinical_gate_authorized':False,'training_release_authorized':False,
                  'privacy':'Output privacy depends on operator-verified parent ACL; POSIX mode is not a Windows ACL attestation.'})
        write_new(output/'browser-evidence.json',{'schema_version':'offline-research-evidence/0.1',
                  'plan_json':raw.decode('utf-8'),'record':record})
        # Only delete the single newly-created snapshot owned by this run.
        if scratch.is_symlink() or scratch.resolve().parent!=output.resolve():raise CandidateInputError('snapshot_cleanup_identity')
        scratch.unlink()
        return record
    except Exception as error:
        if mapped is not None:mapped._mmap.close()
        # Preserve partial evidence/snapshot for the operator. Do not retry.
        write_new(output/'FAILED.json',{'status':'FAILED','reason_code':failure_code(error),'clinical_gate_authorized':False,'training_release_authorized':False})
        raise


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['ct','mask','plan','output']:parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    try:
        record=run_plan(args.ct,args.mask,args.plan,args.output)
        print(json.dumps({'status':'COMPLETE','profile_status':record['profile']['status'],'clinical_gate_authorized':False,'training_release_authorized':False}))
        return 0
    except Exception as error:
        # No patient identifiers, paths, input values or credentials in console logs.
        print(json.dumps({'status':'FAILED','error_type':type(error).__name__,'reason_code':failure_code(error)}),file=sys.stderr)
        return 1


if __name__=='__main__':raise SystemExit(main())
