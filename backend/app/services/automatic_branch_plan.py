"""Offline bridge for admitted raw skeleton trees; never a clinical gate.

The existing extractor's refusal rules are unchanged. Refused graphs are retained
as evidence but can never supply a profile plan's sampling branches.
"""
from copy import deepcopy
import hashlib
import json
import numpy as np
from app.services.experimental_branches import extract_branch_graph
from app.services.experimental_candidates import CandidateInputError


def automatic_branch_plan(mask, geometry, spacing, source):
    graph=extract_branch_graph(mask,geometry,spacing,source)
    result={'schema_version':'automatic-branch-evidence/0.1','method':graph['method'],
        'source':deepcopy(graph['source']),'geometry':deepcopy(graph['geometry']),
        'graph':graph,'status':'abstained','sampling_branches':None,
        'direction_status':'deterministic_order_not_anatomical_proximal_distal',
        'clinical_gate_authorized':False,'training_release_authorized':False}
    if graph['status']=='experimental_tree':
        nodes=graph['nodes'];count=len(nodes);edges={tuple(sorted(e)) for e in graph['edges']}
        partition=[];covered=set();branches=[];affine=np.asarray(graph['geometry']['affine'])
        if not count or [n['node_id'] for n in nodes]!=list(range(count)) or len(edges)!=len(graph['edges']):
            raise CandidateInputError('automatic_graph_integrity_failed')
        for branch in graph['branches']:
            ids=branch['node_ids']
            if len(ids)<3 or len(ids)!=len(set(ids)) or any(type(i) is not int or i<0 or i>=count for i in ids):
                raise CandidateInputError('automatic_graph_integrity_failed')
            ijk=np.asarray([nodes[i]['ijk'] for i in ids]);world=ijk@affine[:3,:3].T+affine[:3,3]
            if (branch['points_ijk']!=ijk.tolist() or not np.allclose(world,branch['points_ras_mm'],rtol=0,atol=1e-10)
                    or branch['mask_sha256']!=source['mask_sha256'] or branch['geometry_fingerprint']!=source['geometry_fingerprint']):
                raise CandidateInputError('automatic_branch_binding_failed')
            partition.extend(tuple(sorted(e)) for e in zip(ids,ids[1:]));covered.update(ids)
            branches.append({key:deepcopy(branch[key]) for key in ['branch_id','ordered','points_ijk','junctions_s_mm','mask_sha256','geometry_fingerprint']})
        if (len(partition)!=len(set(partition)) or set(partition)!=edges or covered!=set(range(count))
                or len(edges)!=count-1 or not branches):raise CandidateInputError('automatic_graph_partition_failed')
        result.update(status='experimental_tree_admitted_for_sampling',sampling_branches=branches)
    # Identity covers refusal evidence as well as admitted paths, without mutation.
    canonical=json.dumps(result,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    if len(canonical)>2*1024*1024:raise CandidateInputError('automatic_branch_document_budget')
    return {**result,'evidence_sha256':hashlib.sha256(canonical).hexdigest()}
