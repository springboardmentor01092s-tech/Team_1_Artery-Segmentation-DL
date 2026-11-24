"""New small analytic acceptance suite, not the frozen twenty-case experiment."""
from copy import deepcopy
import numpy as np
import pytest
from scipy.optimize import linear_sum_assignment
from app.schemas.stenosis import VolumeGeometry
from app.services import automatic_branch_plan as service
from app.services.experimental_candidates import CandidateInputError,ResearchParameters,extract_candidates
from automatic_branch_fixtures import bound_source,y_fixture
from test_branch_characterization import probe


NAMES=['straight','curve','bifurcation','loop','disconnected','noisy_spur','even_width','boundary','narrow','multiple_branches','ambiguous_junction','empty','anisotropic_y','oblique_y']


def fixture(name):
    if name in ['anisotropic_y','oblique_y']:
        mask,g,_,_=y_fixture(2.)
        spacing=np.array([.7,1.1,1.5]) if name=='anisotropic_y' else np.ones(3)
        angle=.3 if name=='oblique_y' else 0.;c,s=np.cos(angle),np.sin(angle)
        affine=np.eye(4);affine[:3,:3]=np.array([[c,0,s],[0,1,0],[-s,0,c]])@np.diag(spacing);affine[:3,3]=[4,-7,9]
        g=VolumeGeometry.model_validate({**g.model_dump(mode='json'),'affine':affine.tolist()})
        def world(points):
            x,y,z=(np.asarray(points)[:,i]*spacing[i] for i in range(3))
            return np.column_stack((c*x+s*z+4,y-7,-s*x+c*z+9))
        tips=world([[36,36,8],[18,36,60],[54,36,60]])
        truth=world(np.concatenate([np.linspace(a,b,201) for a,b in [([36,36,8],[36,36,36]),([36,36,36],[18,36,60]),([36,36,36],[54,36,60])]]))
        return mask,g,spacing,bound_source(mask,g),truth,tips,3
    if name in NAMES[:8]:
        mask,g,spacing,source,truth=probe(name)
        tips=np.array([[36,36,8],[18,36,60],[54,36,60]]) if name=='bifurcation' else truth[[0,-1]]
        return mask,g,spacing,source,truth,tips,3 if name=='bifurcation' else 1
    shape=(81,81,81);ijk=np.stack(np.indices(shape),axis=-1)
    if name=='multiple_branches':
        segments=[([40,40,8],[40,40,28]),([40,40,28],[24,40,48]),([40,40,28],[56,40,48]),([24,40,48],[10,40,68]),([24,40,48],[38,40,68]),([56,40,48],[56,40,68])]
        tips=np.array([[40,40,8],[10,40,68],[38,40,68],[56,40,68]]);expected=5
    elif name=='ambiguous_junction':
        segments=[([40,40,10],[40,40,70]),([10,40,40],[70,40,40]),([40,10,40],[40,70,40])];tips=np.array([p for s in segments for p in s]);expected=6
    else:segments=[([40,40,10],[40,40,70])];tips=np.array([[40,40,10],[40,40,70]]);expected=1
    truth=np.concatenate([np.linspace(a,b,201) for a,b in segments]);distance=np.full(shape,np.inf)
    for a,b in segments:
        a,b=np.array(a),np.array(b);v=b-a;t=np.clip(np.sum((ijk-a)*v,axis=-1)/np.dot(v,v),0,1)
        distance=np.minimum(distance,np.linalg.norm(ijk-a-t[...,None]*v,axis=-1))
    mask=(distance<=(1. if name=='narrow' else 2.)).astype(np.uint8)
    if name=='empty':mask[:]=0
    g=VolumeGeometry(shape=shape,affine=np.eye(4).tolist(),array_axis_order='nifti_i_j_k',world_convention='RAS',world_unit='mm')
    return mask,g,np.ones(3),bound_source(mask,g),truth,tips,expected


def measure(name):
    mask,g,spacing,source,truth,tips,expected=fixture(name);before=mask.copy(),deepcopy(source)
    one=service.automatic_branch_plan(mask,g,spacing,source);two=service.automatic_branch_plan(mask,g,spacing,source)
    assert one==two and np.array_equal(mask,before[0]) and source==before[1]
    graph=one['graph'];nodes=np.array([n['ras_mm'] for n in graph['nodes']]);nerror=coverage=endpoint_error=None
    tolerance=float(np.linalg.norm(spacing))*2
    if len(nodes):
        distances=np.linalg.norm(truth[:,None]-nodes[None,:],axis=-1)
        nerror=float(distances.min(axis=0).max());coverage=float(np.mean(distances.min(axis=1)<=tolerance))
        endpoints=np.array([nodes[p['node_id']] for p in graph['endpoints']])
        if len(endpoints)==len(tips):
            costs=np.linalg.norm(tips[:,None]-endpoints[None,:],axis=-1);a,b=linear_sum_assignment(costs);endpoint_error=float(costs[a,b].max())
    admitted=one['sampling_branches'] is not None;false_branches=missing_branches=None
    if admitted:
        assert len(graph['branches'])==expected and coverage==1.0 and nerror<=tolerance and endpoint_error is not None and endpoint_error<=tolerance
        assert graph['diagnostics']['graph_cycle_rank']==0
        assert one['clinical_gate_authorized'] is one['training_release_authorized'] is False
        if name=='narrow':pairs=np.array([[[40,40,10],[40,40,70]]],dtype=float)
        elif name=='multiple_branches':pairs=np.array([
            [[40,40,8],[40,40,28]],[[40,40,28],[24,40,48]],[[40,40,28],[56,40,68]],
            [[24,40,48],[10,40,68]],[[24,40,48],[38,40,68]]],dtype=float)
        else:
            pairs=np.array([[[36,36,8],[36,36,36]],[[36,36,36],[18,36,60]],[[36,36,36],[54,36,60]]],dtype=float)
            if name in ['anisotropic_y','oblique_y']:
                flat=pairs.reshape(-1,3);scale=np.array([.7,1.1,1.5]) if name=='anisotropic_y' else np.ones(3)
                angle=.3 if name=='oblique_y' else 0.;c,s=np.cos(angle),np.sin(angle)
                x,y,z=(flat[:,i]*scale[i] for i in range(3));pairs=np.column_stack((c*x+s*z+4,y-7,-s*x+c*z+9)).reshape(-1,2,3)
        actual=np.array([[b['points_ras_mm'][0],b['points_ras_mm'][-1]] for b in graph['branches']])
        direct=np.linalg.norm(actual[:,None]-pairs[None,:],axis=-1).max(axis=-1)
        reverse=np.linalg.norm(actual[:,None]-pairs[None,:,::-1],axis=-1).max(axis=-1)
        costs=np.minimum(direct,reverse);a,b=linear_sum_assignment(costs);matched=int(np.count_nonzero(costs[a,b]<=tolerance))
        false_branches=len(actual)-matched;missing_branches=len(pairs)-matched
        assert false_branches==missing_branches==0
    else:assert one['status']=='abstained' and graph['reasons']
    if name in ['loop','disconnected','even_width','boundary','ambiguous_junction','empty']:assert not admitted
    return {'case':name,'admitted':admitted,'reasons':';'.join(graph['reasons']),'branch_count':len(graph['branches']),
        'expected_branches':expected,'false_branches_if_admitted':false_branches,'missing_branches_if_admitted':missing_branches,
        'endpoint_max_mm':endpoint_error,'node_displacement_max_mm':nerror,'truth_coverage_within_two_voxel_diagonals':coverage,
        'cycle_rank':graph['diagnostics'].get('graph_cycle_rank'),'source_unchanged':True,'deterministic':True}


@pytest.mark.parametrize('name',NAMES)
def test_fixed_analytic_acceptance(name):measure(name)


@pytest.mark.parametrize('kind',['singular','spacing','nonfinite','multilabel','wrong_hash'])
def test_invalid_geometry_source_and_labels_are_refused_without_mutation(kind):
    mask,g,spacing,source,*_=fixture('narrow');before=mask.copy()
    if kind=='singular':g=g.model_copy(update={'affine':np.zeros((4,4)).tolist()})
    if kind=='spacing':spacing=[1,1,-1]
    if kind=='nonfinite':g=g.model_copy(update={'affine':[[float('nan')]*4 for _ in range(4)]})
    if kind=='multilabel':mask[1,1,1]=2;before=mask.copy()
    if kind=='wrong_hash':source['mask_sha256']='f'*64
    with pytest.raises((ValueError,CandidateInputError)):service.automatic_branch_plan(mask,g,spacing,source)
    assert np.array_equal(mask,before)


def test_admitted_y_branches_connect_to_existing_sampler_without_changing_algorithm():
    mask,g,spacing,source=y_fixture(2.)
    result=service.automatic_branch_plan(mask,g,spacing,source)
    assert result['sampling_branches'] and len(result['sampling_branches'])==3
    preview=extract_candidates(mask,g,spacing,source,result['sampling_branches'],ResearchParameters(.5,8.,1.,4.,8.,4,.65,2,5.))
    assert preview['source']==source and preview['measurement_status']=='measurement_unavailable_no_validated_gate'
    assert {b['branch_id'] for b in preview['branches']}=={b['branch_id'] for b in result['sampling_branches']}


@pytest.mark.parametrize('kind',['coordinate','duplicate_edge','source_hash'])
def test_bridge_cannot_emit_inconsistent_or_partial_graph_branches(monkeypatch,kind):
    args=y_fixture(2.);original=service.extract_branch_graph(*args)
    if kind=='coordinate':original['branches'][0]['points_ijk'][0][0]+=1
    if kind=='duplicate_edge':original['edges'].append(original['edges'][0])
    if kind=='source_hash':original['branches'][0]['mask_sha256']='f'*64
    monkeypatch.setattr(service,'extract_branch_graph',lambda *args:original)
    with pytest.raises(CandidateInputError):service.automatic_branch_plan(*args)
