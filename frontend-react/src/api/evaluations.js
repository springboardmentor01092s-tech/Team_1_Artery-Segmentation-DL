import api from './client';
import { createEvaluationsApi } from './evaluations-contract';
export const evaluationsApi = createEvaluationsApi(api);
