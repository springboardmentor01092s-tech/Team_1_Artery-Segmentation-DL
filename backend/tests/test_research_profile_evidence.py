"""Independent synthetic evidence for the local simulated assessment workbench.

Run with --noconftest; no model execution, database, datasets or image downloads.
"""
import base64
from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path

import nibabel as nib
import numpy as np
from pydantic import ValidationError
import pytest
from dataclasses import replace

from app.schemas.stenosis import AnalysisResult, VolumeGeometry
from app.schemas.review_annotation import ReviewAnnotation
from app.schemas.review_adjudication import AdjudicationDocument
from app.schemas.evaluation import Metrics
from app.services.experimental_candidates import ResearchParameters, extract_candidates, mask_identity
from app.services.stenosis_geometry import geometry_fingerprint


def procedure_boundary_bundle():
    from test_experimental_candidates import generate_frontend_fixture, PARAMETERS
    bundle=generate_frontend_fixture('flipped')
    image=nib.Nifti1Image.from_bytes(gzip.decompress(base64.b64decode(bundle['mask_gzip_base64'])))
    mask=np.asanyarray(image.dataobj);g=VolumeGeometry.model_validate(bundle['preview']['geometry'])
    source=bundle['preview']['source'];branches=bundle['input_branches']['preview']
    area=next(row['diagnostic_area_mm2'] for row in bundle['preview']['branches'][0]['sections'] if row['sample_ijk'][2]==34)
    reference=next(row['diagnostic_area_mm2'] for row in bundle['preview']['branches'][0]['sections'] if row['sample_ijk'][2]==20)
    equal=area/reference;below=float(np.nextafter(equal,0))
    while reference*below>=area:below=float(np.nextafter(below,0))
    variants={'inclusive_threshold':replace(PARAMETERS,area_ratio_trigger=equal),
              'below_threshold':replace(PARAMETERS,area_ratio_trigger=below),
              'contiguous_six':replace(PARAMETERS,minimum_candidate_sections=6),
              'two_mm_sampling':replace(PARAMETERS,sample_step_mm=2),
              'different_reference_window':replace(PARAMETERS,reference_inner_mm=6,reference_outer_mm=10),
              'insufficient_support':replace(PARAMETERS,minimum_reference_samples_each_side=20)}
    return {'description':'SYNTHETIC PARAMETER BOUNDARY TESTS ONLY; no operating threshold retuning.',
            'variants':{key:extract_candidates(mask,g,[1,1,1],source,branches,p) for key,p in variants.items()}}


def test_procedure_boundary_fixtures_are_exact_backend_outputs():
    path=Path(__file__).resolve().parents[2]/'frontend-react/tests/fixtures/research-procedure-boundaries.json'
    assert json.loads(path.read_text())==procedure_boundary_bundle()


def asymmetric_bundle():
    # Deliberately asymmetric adjacent support, not a clinical lesion phantom.
    # R1 interpolates both sides; R2 uses the smaller side. A disagreement is
    # expected and must remain unresolved, not relabelled by artificial consensus.
    i,j,k = np.indices((33,33,97))
    radius = np.where(k < 34,5.,np.where(k <= 38,4.5,7.))
    mask = ((i-16)**2+(j-16)**2 <= radius**2).astype(np.uint8)
    affine = np.array([[-1,0,0,16],[0,1,0,-16],[0,0,1,-7],[0,0,0,1]])
    geometry = VolumeGeometry(shape=mask.shape,affine=affine.tolist(),array_axis_order='nifti_i_j_k',world_convention='RAS',world_unit='mm')
    images = [nib.Nifti1Image(np.zeros(mask.shape,dtype=np.int16),affine),nib.Nifti1Image(mask,affine)]
    for image in images:image.header.set_xyzt_units('mm')
    ct,labels = [gzip.compress(image.to_bytes(),mtime=0) for image in images]
    ct_sha = hashlib.sha256(ct).hexdigest()
    source = {'source_sha256':ct_sha,'mask_sha256':mask_identity(mask,1),
              'geometry_fingerprint':geometry_fingerprint(geometry,ct_sha),'mask_role':'model_prediction',
              'parent_segmentation_result_id':'12345678-1234-4567-890a-123456789abc','target_label':1}
    branches = [{'branch_id':'main','ordered':True,'points_ijk':[[16.,16.,float(z)] for z in range(4,93)],
                 'junctions_s_mm':[],'mask_sha256':source['mask_sha256'],'geometry_fingerprint':source['geometry_fingerprint']}]
    parameters = ResearchParameters(.5,8.,1.,4.,8.,4,.65,2,5.)
    return {'description':'SYNTHETIC ONLY; asymmetry probes procedural disagreement, not clinical labels or actual model predictions.',
            'ct_gzip_base64':base64.b64encode(ct).decode(),'mask_gzip_base64':base64.b64encode(labels).decode(),
            'input_branches':branches,'preview':extract_candidates(mask,geometry,[1.,1.,1.],source,branches,parameters)}


def test_frontend_asymmetric_evidence_is_actual_backend_extraction():
    path = Path(__file__).resolve().parents[2]/'frontend-react/tests/fixtures/research-asymmetric-profile.json'
    bundle = json.loads(path.read_text())
    assert bundle == asymmetric_bundle()
    image = nib.Nifti1Image.from_bytes(gzip.decompress(base64.b64decode(bundle['mask_gzip_base64'])))
    profile = bundle['preview']
    assert profile['status']=='candidate_preview'
    assert image.header.get_xyzt_units()[0]=='mm'
    assert hashlib.sha256(base64.b64decode(bundle['ct_gzip_base64'])).hexdigest()==profile['source']['source_sha256']
    assert mask_identity(np.asanyarray(image.dataobj),1)==profile['source']['mask_sha256']


@pytest.mark.parametrize('schema',[AnalysisResult,ReviewAnnotation,AdjudicationDocument])
def test_simulated_schema_cannot_be_imported_as_human_review_or_clinical_result(schema):
    payload={'schema_version':'simulated-research-assessment/0.1','clinical_gate_authorized':False,
             'training_release_authorized':False,'records':[],'model_provenance':{'assessment_model':None}}
    before=deepcopy(payload)
    with pytest.raises(ValidationError):schema.model_validate(payload)
    assert payload==before


@pytest.mark.parametrize('schema,base',[
    (ReviewAnnotation,{'schema_version':'independent-lesion-review/0.1','assignment_id':'12345678-1234-4567-890a-123456789abc',
      'source':{'case_id':1,'source_sha256':'a'*64,'shape':[10,10,10],'affine':np.eye(4).tolist(),'units':'mm'},
      'protocol_version':'synthetic-unapproved','status':'unverified_draft','label_origin':'manual_independent_reader_unverified',
      'clinical_gate_authorized':False,'training_release_authorized':False,'reader_qualification_verified':False,
      'reader_independence_verified':False,'case_disposition':'not_assessed','case_unavailable_reason':'Synthetic unassessed fixture','lesions':[]}),
    (AdjudicationDocument,{'schema_version':'review-adjudication/0.1','assignment_id':'12345678-1234-4567-890a-123456789abc',
      'source_sha256':'a'*64,'protocol_version':'synthetic-unapproved','r1_submission_sha256':'b'*64,'r2_submission_sha256':'c'*64,
      'outcome':'not_assessed','reason':'Synthetic unassessed fixture','correspondences':[],'resolutions':[],
      'clinical_gate_authorized':False,'training_release_authorized':False}),
])
def test_otherwise_valid_human_documents_refuse_simulation_payload(schema,base):
    schema.model_validate(base)  # Prove rejection is not a missing-required-field artefact.
    payload={**deepcopy(base),'records':[],'origin':'algorithmic_simulation_on_model_derived_mask'}
    with pytest.raises(ValidationError) as error:schema.model_validate(payload)
    assert any(row['type']=='extra_forbidden' and row['loc']==('origin',) for row in error.value.errors())


def test_research_record_cannot_be_an_evaluation_metric_or_extra_metric_field():
    valid={'dice':0.,'iou':0.,'precision':0.,'recall':0.}
    Metrics.model_validate(valid)  # Real zero segmentation metrics remain legitimate.
    record={'schema_version':'simulated-research-assessment/0.1','clinical_gate_authorized':False,'training_release_authorized':False}
    with pytest.raises(ValidationError):Metrics.model_validate({**valid,'dice':record})
    with pytest.raises(ValidationError):Metrics.model_validate({**valid,'research_record':record})
