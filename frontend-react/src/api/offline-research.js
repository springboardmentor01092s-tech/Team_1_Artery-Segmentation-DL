import api from './client.js';
import {createOfflineResearchApi} from './offline-research-contract.js';
export const offlineResearchApi=createOfflineResearchApi(api);
