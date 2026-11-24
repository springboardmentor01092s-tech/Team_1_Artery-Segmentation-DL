"""Actual assigned-CT route checks with synthetic, disposable PostgreSQL evidence."""
import gzip
import hashlib

import nibabel as nib
import numpy as np
import pytest

from test_annotation_drafts import prepared
from test_review_assignments import pair,assigned


@pytest.mark.parametrize('slot',['R1','R2'])
def test_embedded_source_is_exact_ct_and_cannot_follow_prediction_or_other_reader(client,pair,slot):
    ids=assigned(client,pair);headers=pair['h1' if slot=='R1' else 'h2'];other='R2' if slot=='R1' else 'R1'
    # Make the forbidden prediction unmistakably different from source CT.
    # These are temporary software fixtures, never actual model artifacts.
    (pair['prepared']['folder']/'prediction_mask.nii.gz').write_bytes(b'forbidden synthetic prediction')
    url=f"/api/v1/review-assignments/{ids[slot]}"
    detail=client.get(url,headers=headers).json()
    result=client.get(url+'/source',headers=headers)
    assert result.status_code==200 and result.headers['cache-control']=='no-store'
    assert result.content==pair['prepared']['path'].read_bytes()
    assert hashlib.sha256(result.content).hexdigest()==detail['source']['source_sha256']
    ct=nib.Nifti1Image.from_bytes(gzip.decompress(result.content))
    assert list(ct.shape)==detail['source']['shape']
    np.testing.assert_array_equal(ct.affine,detail['source']['affine'])
    assert detail['clinical_gate_authorized'] is detail['training_release_authorized'] is False
    assert 'segmentation_result_id' not in detail['source']
    assert client.get(f"/api/v1/review-assignments/{ids[other]}/source",headers=headers).status_code==404
    assert client.get(f"/api/v1/review-assignments/{ids[other]}/draft",headers=headers).status_code==404
    case=pair['body']['case_id'];run=pair['prepared']['run_id']
    for path in [f'/cases/{case}/image/metadata',f'/cases/{case}/volume/metadata',f'/cases/{case}/segmentation-config',
                 f'/cases/{case}/segmentations',f'/cases/{case}/segmentations/{run}/source',
                 f'/cases/{case}/segmentations/{run}/mask',f'/cases/{case}/segmentations/{run}/probabilities',
                 f'/cases/{case}/workflow','/evaluations','/stenosis/analytics/summary']:
        assert client.get('/api/v1'+path,headers=headers).status_code==403,path
    # A made-up overlay path cannot grant an alternative source channel.
    assert client.get(url+'/mask',headers=headers).status_code==404
