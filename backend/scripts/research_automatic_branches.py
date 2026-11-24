"""Explicit offline binary-mask → admitted branches → existing profile-plan bridge.

No dataset discovery, resampling, pruning, inference, DB or gate registration.
Four-million-voxel automatic extraction limit remains unchanged.
"""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import nibabel as nib
import numpy as np
from app.schemas.stenosis import VolumeGeometry
from app.services.experimental_candidates import CandidateInputError,ResearchParameters,MAX_VOXELS
from app.services.automatic_branch_plan import automatic_branch_plan
from scripts.research_candidate_profile import sha,write_new,failure_code


def unique(pairs):
    value={}
    for key,item in pairs:
        if key in value:raise CandidateInputError('duplicate_request_property')
        value[key]=item
    return value


def run_request(ct_path,mask_path,request_path,output):
    ct_path,mask_path,request_path,output=map(Path,[ct_path,mask_path,request_path,output])
    if request_path.is_symlink() or request_path.stat().st_size>2*1024*1024:raise CandidateInputError('request_document_budget')
    raw=request_path.read_bytes();request=json.loads(raw,object_pairs_hook=unique)
    fields={'schema_version','dataset_split','spatial_scope','ct_sha256','mask_file_sha256','source','geometry','parameters'}
    if (not isinstance(request,dict) or set(request)!=fields or request['schema_version']!='automatic-branch-request/0.1'
            or request['dataset_split'] not in {'Training','synthetic'} or request['spatial_scope']!='numerical_native_grid_only'):
        raise CandidateInputError('explicit_training_or_synthetic_request_required')
    parameters=ResearchParameters(**request['parameters']);parameters.validate()
    geometry=VolumeGeometry.model_validate(request['geometry'])
    if np.prod(geometry.shape)>MAX_VOXELS:raise CandidateInputError('automatic_mask_resource_limit')
    if any(not p.name.lower().endswith(('.nii','.nii.gz')) for p in [ct_path,mask_path]):raise CandidateInputError('single_file_nifti_sources_required')
    hashes=sha(ct_path),sha(mask_path)
    if hashes!=(request['ct_sha256'],request['mask_file_sha256']) or hashes[0]!=request['source']['source_sha256']:
        raise CandidateInputError('source_file_checksum_mismatch')
    ct,labels=nib.load(ct_path,mmap='r'),nib.load(mask_path,mmap='r')
    for image in [ct,labels]:
        if (len(image.shape)!=3 or tuple(image.shape)!=geometry.shape or image.header.get_xyzt_units()[0]!='mm'
                or not (int(image.header['sform_code'])>0 or int(image.header['qform_code'])>0)
                or not np.array_equal(image.affine,np.asarray(geometry.affine))):raise CandidateInputError('coded_native_mm_geometry_required')
    if (not isinstance(labels,nib.Nifti1Image) or labels.get_data_dtype()!=np.dtype('uint8')
            or labels.dataobj.slope!=1 or labels.dataobj.inter!=0 or not 352<=labels.dataobj.offset<=2*1024*1024):
        raise CandidateInputError('unscaled_uint8_nifti1_mask_required')
    repo=Path(__file__).resolve().parents[2]
    if output.is_symlink() or output.resolve().is_relative_to(repo):raise CandidateInputError('new_external_output_required')
    output.mkdir(mode=0o700,parents=False,exist_ok=False)
    try:
        mask=np.asanyarray(labels.dataobj)
        spacing=np.linalg.norm(np.asarray(geometry.affine)[:3,:3],axis=0)
        result=automatic_branch_plan(mask,geometry,spacing,request['source'])
        if hashes!=(sha(ct_path),sha(mask_path)) or raw!=request_path.read_bytes():raise CandidateInputError('source_changed_during_extraction')
        write_new(output/'branch-evidence.json',result)
        if result['sampling_branches'] is not None:
            plan={**request,'schema_version':'research-profile-plan/0.1','parameters':asdict(parameters),'branches':result['sampling_branches']}
            write_new(output/'profile-plan.json',plan)
        write_new(output/'RUN.json',{'schema_version':'automatic-branch-run/0.1','status':result['status'],
            'source_files':{'ct_sha256':hashes[0],'mask_file_sha256':hashes[1]},'request_sha256':sha(request_path),
            'branch_evidence_sha256':result['evidence_sha256'],'implementation_sha256':{'adapter':sha(Path(__file__).resolve().parents[1]/'app/services/automatic_branch_plan.py'),
                'extractor':sha(Path(__file__).resolve().parents[1]/'app/services/experimental_branches.py'),'orchestrator':sha(Path(__file__))},
            'original_sources_unchanged':True,'clinical_gate_authorized':False,'training_release_authorized':False})
        return result
    except Exception as error:
        write_new(output/'FAILED.json',{'status':'FAILED','reason_code':failure_code(error),'clinical_gate_authorized':False,'training_release_authorized':False})
        raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['ct','mask','request','output']:parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    try:
        result=run_request(args.ct,args.mask,args.request,args.output)
        print(json.dumps({'status':result['status'],'branches':len(result['sampling_branches'] or []),'clinical_gate_authorized':False,'training_release_authorized':False}))
    except Exception as error:
        print(json.dumps({'status':'FAILED','reason_code':failure_code(error)}),file=sys.stderr);raise SystemExit(1)
