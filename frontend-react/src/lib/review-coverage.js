import {POINT_FIELDS} from './annotation-draft.js';

// These are documentation counts, not segment coverage, clinical agreement or labels.
export function reviewCoverage(item){
  return {schema_version:'review-documentation-coverage/0.1',case_id:item.source.case_id,source_sha256:item.source.source_sha256,
    protocol_version:item.protocol_version,scope:'recorded_fields_not_anatomical_coverage_or_correctness',
    readers:item.parents.map((parent,index)=>{
      const doc=parent.submission.document,lesions=doc.lesions;
      return {slot:`R${index+1}`,submission_sha256:parent.record_sha256,case_disposition:doc.case_disposition,recorded_lesion_rows:lesions.length,
        landmarks_recorded:lesions.reduce((n,row)=>n+POINT_FIELDS.filter(field=>row[field]!==null).length,0),landmark_fields:7*lesions.length,
        manual_diameters_recorded:lesions.reduce((n,row)=>n+['minimum_lumen_diameter_mm','adjacent_reference_diameter_mm'].filter(field=>row[field]!==null).length,0),
        qualification_status:'not_established',independence_status:'not_established'};
    }),external_packet_status:'not_bound',evidence_receipts_status:'not_verified',protocol_signoff_status:'not_verified',
    clinical_gate_authorized:false,training_release_authorized:false};
}
