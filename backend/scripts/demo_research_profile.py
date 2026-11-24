"""Generate and execute a reproducible SYNTHETIC offline research demonstration.

No actual model/patient data, database, expert labels or clinical conclusions.
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
from app.services.experimental_candidates import ResearchParameters
from app.services.stenosis_geometry import geometry_fingerprint
from app.services.tiled_candidate_profile import streamed_mask_identity
from research_candidate_profile import run_plan,sha


def run_demo(output):
    output=Path(output)
    if output.is_symlink() or output.resolve().is_relative_to(Path(__file__).resolve().parents[2]):
        raise ValueError('New external output required')
    output.mkdir(mode=0o700,parents=False,exist_ok=False)
    shape=(129,129,257);affine=np.diag([-.7,1.1,1.5,1.]);affine[:3,3]=[50,-50,-80]
    mask=np.zeros(shape,dtype=np.uint8);i,j=np.indices(shape[:2])
    for k in range(shape[2]):
        radius=2.5 if 118<=k<=122 else 5.
        mask[:,:,k]=((.7*(i-64))**2+(1.1*(j-64))**2<=radius**2)
    geometry=VolumeGeometry(shape=shape,affine=affine.tolist(),array_axis_order='nifti_i_j_k',world_convention='RAS',world_unit='mm')
    ct=nib.Nifti1Image(np.zeros(shape,dtype=np.int16),affine);image=nib.Nifti1Image(mask,affine)
    for item in [ct,image]:item.header.set_xyzt_units('mm')
    cp,mp=output/'synthetic-ct.nii.gz',output/'synthetic-mask.nii.gz';nib.save(ct,cp);nib.save(image,mp)
    geometry=VolumeGeometry.model_validate({**geometry.model_dump(mode='json'),'affine':nib.load(cp).affine.tolist()})
    source={'source_sha256':sha(cp),'mask_sha256':streamed_mask_identity(mask,1),'geometry_fingerprint':geometry_fingerprint(geometry,sha(cp)),
            'mask_role':'supplied_segmentation','parent_segmentation_result_id':None,'target_label':1}
    branches=[{'branch_id':'synthetic','ordered':True,'points_ijk':[[64.,64.,float(k)] for k in np.arange(100,151,1/1.5)],
               'junctions_s_mm':[],'mask_sha256':source['mask_sha256'],'geometry_fingerprint':source['geometry_fingerprint']}]
    plan={'schema_version':'research-profile-plan/0.1','dataset_split':'synthetic','spatial_scope':'numerical_native_grid_only',
          'ct_sha256':sha(cp),'mask_file_sha256':sha(mp),'source':source,'geometry':geometry.model_dump(mode='json'),
          'branches':branches,'parameters':asdict(ResearchParameters(.5,8.,1.,4.,8.,4,.65,2,5.))}
    pp=output/'plan.json';pp.write_text(json.dumps(plan,indent=2),encoding='utf-8')
    (output/'SYNTHETIC-ONLY.txt').write_text('Mathematical test fixture, not original CT, actual model prediction, expert annotation or medical ground truth.\n',encoding='utf-8')
    result=run_plan(cp,mp,pp,output/'profile-run')
    print(json.dumps({'status':'COMPLETE','synthetic_only':True,'voxels':int(np.prod(shape)),
      'profile_status':result['profile']['status'],'candidates':len(result['profile']['candidates']),
      'clinical_gate_authorized':False,'training_release_authorized':False}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    run_demo(parser.parse_args().output)
