import api from './client.js';
import {validateRealVolumeResearch} from './real-volume-research-contract.js';

export async function analyzeRealVolumeResearch({ctVolume, vesselMask, signal}, client = api) {
  if (!(ctVolume instanceof Blob) || !(vesselMask instanceof Blob)) {
    throw new Error('Choose both a CT NIfTI and its matching binary mask.');
  }
  const form = new FormData();
  form.append('ct_volume', ctVolume, ctVolume.name || 'ct.nii');
  form.append('vessel_mask', vesselMask, vesselMask.name || 'mask.nii');
  const response = await client.post('/experimental-stenosis/real-volume/analyze', form, {
    signal, headers: {'Content-Type': undefined},
  });
  if (response.status !== 200) throw new Error('Real-volume research analysis failed.');
  return validateRealVolumeResearch(response.data);
}
