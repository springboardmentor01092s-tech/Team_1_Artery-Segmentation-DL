// Synthetic API contract evidence only; never imported by production UI.
export const runFixture = {
  segmentation_result_id:'44444444-1234-4567-890a-123456789abc',created_at:'2026-11-13T01:00:00Z',
  source_sha256:'a'.repeat(64),checkpoint_sha256:'b'.repeat(64),mask_sha256:'c'.repeat(64),probabilities_sha256:'d'.repeat(64),threshold:0.7,
};
export function workflowFixture({caseId=1, reviewed=false, outcome='accepted_for_research'}={}) {
  const review = reviewed ? {id:'55555555-1234-4567-890a-123456789abc',case_id:caseId,...runFixture,
    reviewer_id:1,reviewer_role:'Admin',reviewed_at:'2026-11-13T02:00:00Z',outcome,note:'Inspected synthetic research output.',
    current:true,scope:'research_workflow_v1'} : null;
  return {case_id:caseId,case_status:reviewed ? outcome==='accepted_for_research'?'complete':'changes_requested':'awaiting_review',
    model_analysis:{available:true,reason:null,run:{...runFixture}},review,review_history:review?[review]:[],
    review_requires_new_run:false,research_only:true,clinical_validation:false};
}
