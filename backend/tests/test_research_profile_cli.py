"""Offline file-bound run tests, using only newly generated synthetic files."""
import hashlib
import importlib.util
import json
from pathlib import Path
import nibabel as nib
import numpy as np
import pytest
from dataclasses import asdict
from app.schemas.stenosis import VolumeGeometry
from test_experimental_candidates import fixture,PARAMETERS

SPEC=importlib.util.spec_from_file_location('profile_cli',Path(__file__).resolve().parents[1]/'scripts/research_candidate_profile.py')
cli=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(cli)


def inputs(tmp_path,kind='focal'):
    mask,g,spacing,source,branches,_=fixture(kind)
    ct=nib.Nifti1Image(np.zeros(mask.shape,dtype=np.int16),g.affine)
    image=nib.Nifti1Image(mask,g.affine)
    for item in [ct,image]:item.header.set_xyzt_units('mm')
    cp,mp=tmp_path/'synthetic-ct.nii.gz',tmp_path/'synthetic-mask.nii.gz'
    nib.save(ct,cp);nib.save(image,mp)
    g=VolumeGeometry.model_validate({**g.model_dump(mode='json'),'affine':nib.load(cp).affine.tolist()})
    source['source_sha256']=cli.sha(cp)
    from app.services.stenosis_geometry import geometry_fingerprint
    source['geometry_fingerprint']=geometry_fingerprint(g,source['source_sha256'])
    for b in branches:b['geometry_fingerprint']=source['geometry_fingerprint']
    plan={'schema_version':'research-profile-plan/0.1','dataset_split':'synthetic','spatial_scope':'numerical_native_grid_only',
          'ct_sha256':cli.sha(cp),'mask_file_sha256':cli.sha(mp),'source':source,'geometry':g.model_dump(mode='json'),
          'branches':branches,'parameters':asdict(PARAMETERS)}
    pp=tmp_path/'plan.json';pp.write_text(json.dumps(plan));return cp,mp,pp,plan


@pytest.mark.parametrize('kind',['focal','anisotropic','oblique','empty','disconnected','source-boundary'])
def test_real_nifti_cli_run_preserves_inputs_and_native_frame(tmp_path,kind):
    cp,mp,pp,plan=inputs(tmp_path,kind);before=[cli.sha(p) for p in [cp,mp,pp]]
    result=cli.run_plan(cp,mp,pp,tmp_path/'run')
    assert result['profile']['source']==plan['source']
    assert result['clinical_gate_authorized'] is result['training_release_authorized'] is False
    assert [cli.sha(p) for p in [cp,mp,pp]]==before
    assert not (tmp_path/'run/mask-snapshot.nii').exists()
    assert json.loads((tmp_path/'run/RUN.json').read_text())['original_sources_unchanged'] is True


@pytest.mark.parametrize('kind',['ct_hash','mask_hash','Testing','Validation','unknown_ct_units','unknown_mask_units','geometry','rounded_geometry','dtype','nifti2','expansion','collision','inside_repo'])
def test_invalid_plan_or_source_never_publishes_success(tmp_path,monkeypatch,kind):
    cp,mp,pp,plan=inputs(tmp_path);output=tmp_path/'run'
    if kind=='ct_hash':plan['ct_sha256']='f'*64
    if kind=='mask_hash':plan['mask_file_sha256']='f'*64
    if kind in {'Testing','Validation'}:plan['dataset_split']=kind
    if kind in {'unknown_ct_units','unknown_mask_units','dtype','nifti2'}:
        p=cp if kind=='unknown_ct_units' else mp;old=nib.load(p);data=np.asanyarray(old.dataobj)
        cls=nib.Nifti2Image if kind=='nifti2' else nib.Nifti1Image
        image=cls(data.astype(np.int16) if kind=='dtype' else data,old.affine)
        image.header.set_xyzt_units('mm' if kind in {'dtype','nifti2'} else 'unknown');nib.save(image,p)
        plan['ct_sha256']=cli.sha(cp);plan['source']['source_sha256']=plan['ct_sha256'];plan['mask_file_sha256']=cli.sha(mp)
    if kind=='geometry':plan['geometry']['affine'][0][3]+=1
    if kind=='rounded_geometry':plan['geometry']['affine'][0][3]+=1e-8
    if kind=='expansion':monkeypatch.setattr(cli,'MAX_MASK_BYTES',4096)
    if kind=='collision':output.mkdir();(output/'keep.txt').write_text('preserve')
    if kind=='inside_repo':output=Path(__file__).resolve().parents[2]/'never-created-profile-output'
    pp.write_text(json.dumps(plan));before=[cli.sha(p) for p in [cp,mp,pp]]
    with pytest.raises((ValueError,FileExistsError)):cli.run_plan(cp,mp,pp,output)
    assert not (output/'profile.json').exists()
    assert [cli.sha(p) for p in [cp,mp,pp]]==before
    if kind=='collision':assert (output/'keep.txt').read_text()=='preserve'
    if (output/'FAILED.json').exists():
        failure=json.loads((output/'FAILED.json').read_text())
        assert failure['reason_code'] and str(tmp_path) not in failure['reason_code']


def test_changed_input_during_sampling_is_detected_before_publication(tmp_path,monkeypatch):
    cp,mp,pp,_=inputs(tmp_path);original=cli.extract_tiled_candidates
    def changed(*args):
        result=original(*args)
        with mp.open('ab') as stream:stream.write(b'changed synthetic input')
        return result
    monkeypatch.setattr(cli,'extract_tiled_candidates',changed)
    with pytest.raises(ValueError,match='source_changed'):cli.run_plan(cp,mp,pp,tmp_path/'run')
    assert not (tmp_path/'run/profile.json').exists()


def test_console_failure_codes_do_not_disclose_paths_or_input_values():
    assert cli.failure_code(FileExistsError('private/source/path'))=='output_collision'
    assert cli.failure_code(ValueError('private medical contents'))=='invalid_input_or_profile_failure'
    assert cli.failure_code(cli.CandidateInputError('mask_scale_or_units_unresolved'))=='mask_scale_or_units_unresolved'
