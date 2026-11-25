import api from './client.js';
import {validateSyntheticAnalysis, validateSyntheticSample, validateSyntheticStatus} from './experimental-stenosis-contract.js';

export function createExperimentalStenosisApi(client) {
  return {
    async status({signal} = {}) {
      const response = await client.get('/experimental-stenosis/status', {signal});
      if (response.status !== 200) throw new Error('Research model status unavailable.');
      return validateSyntheticStatus(response.data);
    },
    async sample(request, {signal} = {}) {
      const response = await client.post('/experimental-stenosis/samples', request, {signal});
      if (response.status !== 200) throw new Error('Synthetic sample generation failed.');
      return validateSyntheticSample(response.data);
    },
    async analyze(request, {signal} = {}) {
      const response = await client.post('/experimental-stenosis/analyze', request, {signal});
      if (response.status !== 200) throw new Error('Experimental analysis failed.');
      return validateSyntheticAnalysis(response.data);
    },
  };
}

export const experimentalStenosisApi = createExperimentalStenosisApi(api);
