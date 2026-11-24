"""New small deterministic topology probes; never reruns the frozen 20-case matrix."""
from copy import deepcopy
import numpy as np
import pytest
from app.schemas.stenosis import VolumeGeometry
from app.services.experimental_branches import extract_branch_graph
from automatic_branch_fixtures import bound_source,y_fixture


def probe(name):
    spacing=np.array([.8,1.,1.2]);shape=(57,57,57)
    i,j,k=np.indices(shape,dtype=float)
    # Independent explicit physical coordinate formula; not production affine.
    world=np.stack(((i-28)*.8,(j-28),(k-28)*1.2),axis=-1)
    if name=='bifurcation':
        mask,g,spacing,source=y_fixture(2.)
        truth=np.concatenate([np.linspace(a,b,121) for a,b in [([36,36,8],[36,36,36]),([36,36,36],[18,36,60]),([36,36,36],[54,36,60])]])
        return mask,g,np.array(spacing),source,truth
    if name=='curve':
        t=np.linspace(-.65,.65,161);truth=np.column_stack((22*(1-np.cos(t)),np.zeros_like(t),22*np.sin(t)))
    elif name=='loop':
        t=np.linspace(0,2*np.pi,241);truth=np.column_stack((12*np.cos(t),12*np.sin(t),np.zeros_like(t)))
    else:truth=np.column_stack((np.zeros(161),np.zeros(161),np.linspace(-18,18,161)))
    distance=np.full(shape,np.inf)
    for point in truth:distance=np.minimum(distance,np.linalg.norm(world-point,axis=-1))
    mask=(distance<=2.4).astype(np.uint8)
    if name=='disconnected':mask[4:7,4:7,4:7]=1
    if name=='noisy_spur':mask[28:36,27:30,27:30]=1
    if name=='boundary':mask[28,28,:]=1
    if name=='even_width':
        mask[:]=0;mask[26:30,26:30,10:47]=1
    affine=np.diag([.8,1.,1.2,1.]);affine[:3,3]=[-22.4,-28,-33.6]
    g=VolumeGeometry(shape=shape,affine=affine.tolist(),array_axis_order='nifti_i_j_k',world_convention='RAS',world_unit='mm')
    return mask,g,spacing,bound_source(mask,g),truth


def characterize(name):
    mask,g,spacing,source,truth=probe(name);before=mask.copy(),deepcopy(source)
    first=extract_branch_graph(mask,g,spacing,source);second=extract_branch_graph(mask,g,spacing,source)
    assert first==second and np.array_equal(mask,before[0]) and source==before[1]
    nodes=np.asarray([n['ras_mm'] for n in first['nodes']]);node_error=truth_error=None
    if len(nodes):
        ijk=np.asarray([n['ijk'] for n in first['nodes']]);assert np.all(mask[tuple(ijk.T)]==1)
        if name!='bifurcation':
            independent=np.column_stack(((ijk[:,0]-28)*.8,ijk[:,1]-28,(ijk[:,2]-28)*1.2))
            assert np.allclose(nodes,independent,atol=1e-12)
        distances=np.linalg.norm(nodes[:,None]-truth[None,:],axis=-1)
        node_error=float(distances.min(axis=1).max());truth_error=float(distances.min(axis=0).max())
    if first['status']=='experimental_tree':
        edges=[tuple(sorted(e)) for b in first['branches'] for e in zip(b['node_ids'],b['node_ids'][1:])]
        assert len(edges)==len(set(edges)) and set(edges)=={tuple(e) for e in first['edges']}
        assert node_error<=float(np.linalg.norm(spacing))*2
    if name in {'loop','disconnected','boundary'}:assert first['status']=='abstained'
    return {'probe':name,'status':first['status'],'reasons':';'.join(first['reasons']),'nodes':len(first['nodes']),
        'branches':len(first['branches']),'node_to_truth_max_mm':node_error,'truth_to_node_max_mm':truth_error,
        'metrics_scope':'sampled analytic centerline; symmetric nearest-point maxima, not anatomical validation',
        'source_unchanged':True,'deterministic':True}


@pytest.mark.parametrize('name',['straight','curve','bifurcation','loop','disconnected','noisy_spur','even_width','boundary'])
def test_small_topology_and_geometry_characterization(name):
    characterize(name)
