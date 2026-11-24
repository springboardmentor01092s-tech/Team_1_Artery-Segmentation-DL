import api from './client';
import { createReferenceProfilesApi } from './reference-profiles-contract';
export const loadReferenceProfiles = createReferenceProfilesApi(api);
