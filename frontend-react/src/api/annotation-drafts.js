import api from './client.js';
import { createAnnotationDraftApi } from './annotation-drafts-contract.js';

export const annotationDraftsApi=createAnnotationDraftApi(api);
