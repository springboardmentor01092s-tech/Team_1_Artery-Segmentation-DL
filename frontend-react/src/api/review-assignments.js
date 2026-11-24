import api from './client.js';
import {createReviewAssignmentsApi} from './review-assignments-contract.js';
export const reviewAssignmentsApi=createReviewAssignmentsApi(api);
