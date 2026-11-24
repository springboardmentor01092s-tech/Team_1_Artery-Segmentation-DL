from dataclasses import asdict
import json
from pathlib import Path
import nibabel as nib
import numpy as np
import pytest
from automatic_branch_fixtures import y_fixture
from scripts.research_automatic_branches import run_request
from scripts.research_candidate_profile import run_plan,sha
from app.services.experimental_candidates import ResearchParameters
from app.services.stenosis_geometry import geometry_fingerprint


def inputs(tmp):
    mask,g,spacing,source=y_fixture(2.)
    ct=nib.Nifti1Image(np.zeros(mask.shape,dtype=np.int16),g.affine);labels=nib.Nifti1Image(mask,g.affine)
    for item in [ct,labels]:item.header.set_xyzt_units('mm')
    cp,mp=tmp/'ct.nii.gz',tmp/'mask.nii.gz';nib.save(ct,cp);nib.save(labels,mp)
    source['source_sha256']=sha(cp);source['geometry_fingerprint']=geometry_fingerprint(g,source['source_sha256'])
    value={'schema_version':'automatic-branch-request/0.1','dataset_split':'synthetic','spatial_scope':'numerical_native_grid_only',
        'ct_sha256':sha(cp),'mask_file_sha256':sha(mp),'source':source,'geometry':g.model_dump(mode='json'),
        'parameters':asdict(ResearchParameters(.5,8.,1.,4.,8.,4,.65,2,5.))}
    pp=tmp/'request.json';pp.write_text(json.dumps(value),encoding='utf-8');return cp,mp,pp,value


def test_real_nifti_automatic_branch_plan_replays_existing_profile_producer(tmp_path):
    cp,mp,pp,value=inputs(tmp_path);before=sha(cp),sha(mp),sha(pp)
    result=run_request(cp,mp,pp,tmp_path/'automatic')
    assert result['status']=='experimental_tree_admitted_for_sampling' and len(result['sampling_branches'])==3
    record=run_plan(cp,mp,tmp_path/'automatic/profile-plan.json',tmp_path/'profiles')
    assert record['profile']['source']==value['source'] and len(record['profile']['branches'])==3
    assert record['clinical_gate_authorized'] is record['training_release_authorized'] is False
    assert before==(sha(cp),sha(mp),sha(pp))
    assert (tmp_path/'profiles/browser-evidence.json').is_file()


@pytest.mark.parametrize('kind',['Testing','Validation','hash','units','labels','collision','geometry','oversized','parameters'])
def test_invalid_request_never_emits_a_sampling_plan_or_changes_sources(tmp_path,kind):
    cp,mp,pp,value=inputs(tmp_path);output=tmp_path/'out'
    if kind in {'Testing','Validation'}:value['dataset_split']=kind
    if kind=='hash':value['ct_sha256']='f'*64
    if kind=='geometry':value['geometry']['affine'][0][3]+=1
    if kind=='oversized':value['geometry']['shape']=[201,201,201]
    if kind=='parameters':value['parameters']['sample_step_mm']=0
    if kind in {'units','labels'}:
        image=nib.load(mp);data=np.asanyarray(image.dataobj)
        if kind=='labels':data=data.copy();data[0,0,0]=2
        replacement=nib.Nifti1Image(data,image.affine);replacement.header.set_xyzt_units('unknown' if kind=='units' else 'mm');nib.save(replacement,mp)
        value['mask_file_sha256']=sha(mp)
    if kind=='collision':output.mkdir();(output/'keep.txt').write_text('preserve')
    pp.write_text(json.dumps(value),encoding='utf-8');before=sha(cp),sha(mp),sha(pp)
    with pytest.raises((ValueError,OSError)):run_request(cp,mp,pp,output)
    assert not (output/'profile-plan.json').exists() and before==(sha(cp),sha(mp),sha(pp))
    if kind=='collision':assert (output/'keep.txt').read_text()=='preserve'
