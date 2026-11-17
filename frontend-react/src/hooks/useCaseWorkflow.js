import { useCallback } from 'react';
import { casesApi } from '../api/cases';
import { useRemote } from './useRemote';

export function useCaseWorkflow(caseId) {
  const remote = useRemote(useCallback(() => casesApi.workflow(caseId), [caseId]));
  // Never display evidence from the previous route during an async transition.
  return { ...remote, data: remote.data?.case_id === Number(caseId) ? remote.data : null };
}
