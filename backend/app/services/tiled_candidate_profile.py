"""Offline bounded scans, with the unchanged supplied-branch plane operator.

No API, database, model inference or automatic branch extraction. All source voxels
are validated/hashed; no crop, resampling, smoothing or component removal occurs.
"""
import hashlib
import struct

import numpy as np
from scipy.ndimage import label

from app.services.experimental_candidates import (
    CandidateInputError, MASK_PREFIX, ResearchParameters, _geometry, _sample_profile, _validate_source,
)
from app.services.stenosis_geometry import geometry_fingerprint

MAX_FULL_VOXELS = 134_217_728
MAX_SLICE_PIXELS = 1_048_576
MAX_ACTIVE_LABELS = 65_536
HASH_SLAB_VALUES = 262_144


def validate_storage(mask, target):
    # Only already mapped categorical bytes, never an implicit ndarray conversion.
    if not isinstance(mask, np.ndarray) or mask.dtype != np.uint8 or mask.ndim != 3:
        raise CandidateInputError('mapped_uint8_categorical_mask_required')
    if any(n < 2 for n in mask.shape) or mask.size > MAX_FULL_VOXELS or mask.shape[0]*mask.shape[1] > MAX_SLICE_PIXELS:
        raise CandidateInputError('full_volume_storage_budget')
    if isinstance(target, bool) or not isinstance(target, int) or not 1 <= target <= 255:
        raise CandidateInputError('explicit_uint8_target_label_required')


def streamed_mask_identity(mask, target):
    """Same canonical C-order uint32 LE identity as the original small operator."""
    validate_storage(mask,target)
    digest=hashlib.sha256(MASK_PREFIX+struct.pack('<4I',*mask.shape,target))
    # nditer buffers strided/Fortran mapped inputs without flattening the volume.
    with np.nditer(mask,flags=['external_loop','buffered'],order='C',
                   op_flags=['readonly'],buffersize=HASH_SLAB_VALUES) as iterator:
        for slab in iterator:digest.update(np.asarray(slab,dtype='<u4').tobytes())
    return digest.hexdigest()


def streamed_component_count(mask,target):
    """Exact six-connected component count with one previous-slice frontier.

    A component is finalized only when its root leaves the frontier. Active roots
    are compacted every slice, so storage depends on slice size, not volume depth.
    Pathological frontiers explicitly refuse rather than lose components.
    """
    validate_storage(mask,target)
    previous=np.zeros(mask.shape[:2],dtype=np.int32);active=0;finished=0
    for k in range(mask.shape[2]):
        current,count=label(np.asarray(mask[:,:,k])==target)  # default 4-connected 2D
        if active+count > MAX_ACTIVE_LABELS:
            raise CandidateInputError('component_frontier_budget')
        current[current>0]+=active
        parents=np.arange(active+count+1,dtype=np.int32)
        def find(n):
            while parents[n]!=n:
                parents[n]=parents[parents[n]];n=int(parents[n])
            return n
        overlap=(previous>0)&(current>0)
        if overlap.any():
            pairs=np.unique(np.stack([previous[overlap],current[overlap]],axis=1),axis=0)
            for a,b in pairs:
                a,b=find(int(a)),find(int(b))
                if a!=b:parents[max(a,b)]=min(a,b)
        roots=np.array([find(i) for i in range(active+count+1)],dtype=np.int32)
        old_roots=np.unique(roots[1:active+1]);new_roots=np.unique(roots[active+1:])
        finished+=len(np.setdiff1d(old_roots,new_roots,assume_unique=True))
        remap=np.zeros(active+count+1,dtype=np.int32)
        if len(new_roots):
            mapping={int(root):i+1 for i,root in enumerate(new_roots)}
            remap[active+1:]=[mapping[int(root)] for root in roots[active+1:]]
        previous=remap[current];active=len(new_roots)
    return finished+active


class _TargetMask:
    def __init__(self,mask,target):self.mask=mask;self.target=target;self.shape=mask.shape
    def __getitem__(self,index):return self.mask[index]==self.target


def extract_tiled_candidates(mask,geometry,spacing,source,branches,parameters):
    if not isinstance(parameters,ResearchParameters):raise CandidateInputError('explicit_research_parameters_required')
    n=parameters.validate();_validate_source(source);validate_storage(mask,source['target_label'])
    g,affine,inverse=_geometry(mask,geometry,spacing)
    if streamed_mask_identity(mask,source['target_label'])!=source['mask_sha256'] or geometry_fingerprint(g,source['source_sha256'])!=source['geometry_fingerprint']:
        raise CandidateInputError('source_identity_mismatch')
    count=streamed_component_count(mask,source['target_label'])
    return _sample_profile(_TargetMask(mask,source['target_label']),g,affine,inverse,source,branches,parameters,n,count)
