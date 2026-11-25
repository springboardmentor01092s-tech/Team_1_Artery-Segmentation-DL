"""Synthetic bounded-volume parity; no application/database fixtures."""
from copy import deepcopy
from dataclasses import replace
import numpy as np
import pytest
from scipy.ndimage import label

from app.services.experimental_candidates import CandidateInputError, extract_candidates, mask_identity
from app.services.tiled_candidate_profile import (
    extract_tiled_candidates, streamed_mask_identity, streamed_component_count, validate_storage,
)
from app.services.stenosis_geometry import geometry_fingerprint
from app.schemas.stenosis import VolumeGeometry
from test_experimental_candidates import fixture, PARAMETERS


@pytest.mark.parametrize('kind',['uniform','focal','multiple','anisotropic','oblique','branching','disconnected','empty','short','pocket','source-boundary'])
def test_all_existing_research_profiles_match_without_numerical_changes(kind):
    mask,g,spacing,source,branches,_=fixture(kind)
    before=mask.copy(),deepcopy(branches),deepcopy(source)
    assert extract_tiled_candidates(mask,g,spacing,source,branches,PARAMETERS)==extract_candidates(mask,g,spacing,source,branches,PARAMETERS)
    assert streamed_mask_identity(np.asfortranarray(mask),1)==mask_identity(mask,1)
    assert np.array_equal(mask,before[0]) and branches==before[1] and source==before[2]


@pytest.mark.parametrize('seed',range(20))
def test_frontier_connectivity_matches_independent_full_scipy_label(seed):
    rng=np.random.default_rng(seed)
    for density in [0,.1,.5,.9,1]:
        mask=(rng.random((9,11,13))<density).astype(np.uint8)
        assert streamed_component_count(mask,1)==label(mask)[1]


def test_late_bridge_and_completed_components_are_not_discarded():
    mask=np.zeros((9,9,10),dtype=np.uint8)
    mask[2,2,:]=1;mask[6,2,:]=1;mask[2:7,2,9]=1
    assert streamed_component_count(mask,1)==1
    mask[2:7,2,9]=0
    assert streamed_component_count(mask,1)==2
    mask[:]=0;mask[2,2,1]=1;mask[2,2,8]=1
    assert streamed_component_count(mask,1)==2


def test_large_native_mapped_mask_exceeds_old_array_limit_without_cropping(tmp_path):
    # >4 million real mapped voxels, fixed native coordinates. No huge mock shape.
    mask=np.memmap(tmp_path/'synthetic.u8',mode='w+',dtype=np.uint8,shape=(129,129,257),order='F')
    mask[:]=0
    i,j=np.indices((129,129));section=((i-64)**2+(j-64)**2<=25).astype(np.uint8)
    for k in range(257):mask[:,:,k]=section
    g={'shape':list(mask.shape),'affine':np.eye(4).tolist(),'array_axis_order':'nifti_i_j_k','world_convention':'RAS','world_unit':'mm'}
    source={'source_sha256':'a'*64,'mask_sha256':streamed_mask_identity(mask,1),'geometry_fingerprint':geometry_fingerprint(VolumeGeometry.model_validate(g),'a'*64),
            'mask_role':'supplied_segmentation','parent_segmentation_result_id':None,'target_label':1}
    branches=[{'branch_id':'native','ordered':True,'points_ijk':[[64.,64.,float(k)] for k in range(4,93)],'junctions_s_mm':[],
               'mask_sha256':source['mask_sha256'],'geometry_fingerprint':source['geometry_fingerprint']}]
    with pytest.raises(CandidateInputError,match='resource_limit'):extract_candidates(mask,g,[1,1,1],source,branches,PARAMETERS)
    result=extract_tiled_candidates(mask,g,[1,1,1],source,branches,PARAMETERS)
    assert result['status']=='no_candidates_in_evaluable_sections'
    assert result['geometry']['shape']==[129,129,257]
    assert result['branches'][0]['sections'][0]['sample_ijk']==[64.,64.,4.]
    mask._mmap.close()


@pytest.mark.parametrize('kind',['float','dimensions','oversize','slice','target','frontier','singular','shear','source'])
def test_invalid_or_unbounded_inputs_fail_explicitly(kind):
    mask,g,spacing,source,branches,_=fixture()
    g=g.model_dump(mode='json')
    if kind=='float':mask=mask.astype(np.float32)
    if kind=='dimensions':mask=mask[:,:,0]
    if kind=='oversize':
        view=np.lib.stride_tricks.as_strided(np.zeros(1,dtype=np.uint8),shape=(512,512,513),strides=(0,0,0))
        with pytest.raises(CandidateInputError,match='budget'):validate_storage(view,1)
        return
    if kind=='slice':
        view=np.lib.stride_tricks.as_strided(np.zeros(1,dtype=np.uint8),shape=(1025,1025,2),strides=(0,0,0))
        with pytest.raises(CandidateInputError,match='budget'):validate_storage(view,1)
        return
    if kind=='target':source['target_label']=True
    if kind=='frontier':
        i,j=np.indices((400,400));chess=np.repeat(((i+j)%2).astype(np.uint8)[:,:,None],2,axis=2)
        with pytest.raises(CandidateInputError,match='frontier_budget'):streamed_component_count(chess,1)
        return
    if kind=='singular':g['affine'][0]=[0,0,0,0]
    if kind=='shear':g['affine'][0][1]=.1
    if kind=='source':source['mask_sha256']='f'*64
    with pytest.raises(ValueError):extract_tiled_candidates(mask,g,spacing,source,branches,PARAMETERS)


@pytest.mark.parametrize('value',['invalid',None,[],True,float('nan'),float('inf')])
def test_malformed_parameter_values_raise_controlled_refusal(value):
    with pytest.raises(CandidateInputError):replace(PARAMETERS,plane_pitch_mm=value).validate()


def test_invalid_parameter_does_not_deepcopy_or_allocate_user_payload():
    class NoCopy:
        def __deepcopy__(self,memo):raise AssertionError('Invalid parameter was copied before validation')
    with pytest.raises(CandidateInputError):replace(PARAMETERS,plane_pitch_mm=NoCopy()).validate()


@pytest.mark.parametrize('pitch,radius',[(1e-200,1e-200),(1e200,1e200),(1e-200,1e200)])
def test_overflow_or_underflow_plane_parameters_refuse_before_allocation(pitch,radius):
    with pytest.raises(CandidateInputError):replace(PARAMETERS,plane_pitch_mm=pitch,plane_radius_mm=radius).validate()


@pytest.mark.parametrize('value',[None,1,[],{},'invalid branch'])
def test_malformed_branch_identity_is_an_explicit_input_error(value):
    mask,g,spacing,source,branches,_=fixture()
    branches[0]['branch_id']=value
    with pytest.raises(CandidateInputError):extract_tiled_candidates(mask,g,spacing,source,branches,PARAMETERS)
