import {validateNativeGeometry,newDraftLesion,POINT_FIELDS,SEVERITY_CHOICES} from './annotation-draft.js';
export const REVIEW_ANNOTATION_VERSION='independent-lesion-review/0.1';
const HASH=/^[a-f0-9]{64}$/,UUID=/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i;
const exact=(v,keys)=>v&&typeof v==='object'&&!Array.isArray(v)&&Object.keys(v).length===keys.length&&keys.every(k=>Object.hasOwn(v,k));
const fail=()=>{throw new Error('Invalid or source-mismatched manual review worksheet. No clinical result was imported.');};
const text=(v,max)=>typeof v==='string'&&v.length<=max;
const canonical=v=>JSON.stringify(v,(_,x)=>x&&typeof x==='object'&&!Array.isArray(x)?Object.fromEntries(Object.keys(x).sort().map(k=>[k,x[k]])):x);
const LESION_KEYS=['draft_id','artery','segment','segment_convention',...POINT_FIELDS,'minimum_lumen_diameter_mm','adjacent_reference_diameter_mm',
  'reference_selection','percentage_narrowing','percentage_basis','severity_category','unavailable_reason','notes','measurement_method','measurement_evidence'];
export function newReaderLesion(){return {...newDraftLesion(),measurement_method:'',measurement_evidence:''};}
export function manualNativeLandmark(text,source){
  validateNativeGeometry(source);
  if(typeof text!=='string'||text.length>200)throw new Error('Enter three original native IJK coordinates.');
  const clean=text.trim(),parts=clean.includes(',')?clean.split(',').map(v=>v.trim()):clean.split(/\s+/),decimal=/^[+-]?(?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?$/i;
  if(parts.length!==3||!parts.every(v=>decimal.test(v)))throw new Error('Enter three finite native IJK numbers, separated by commas or spaces.');
  const point=parts.map(Number);
  if(!point.every((n,i)=>Number.isFinite(n)&&n>=0&&n<=source.shape[i]-1))throw new Error('Manual landmark is outside the original native CT grid.');
  return point;
}
export function newReviewAnnotation(item){
  validateNativeGeometry(item.source);
  return {schema_version:REVIEW_ANNOTATION_VERSION,assignment_id:item.id,source:structuredClone(item.source),protocol_version:item.protocol_version,
    status:'unverified_draft',label_origin:'manual_independent_reader_unverified',clinical_gate_authorized:false,training_release_authorized:false,
    reader_qualification_verified:false,reader_independence_verified:false,case_disposition:'not_assessed',case_unavailable_reason:'Not assessed; manual reader entry required.',lesions:[]};
}
export function validateReviewAnnotation(value,item){
  validateNativeGeometry(item.source);
  if(!exact(value,['schema_version','assignment_id','source','protocol_version','status','label_origin','clinical_gate_authorized','training_release_authorized',
    'reader_qualification_verified','reader_independence_verified','case_disposition','case_unavailable_reason','lesions'])
    ||value.schema_version!==REVIEW_ANNOTATION_VERSION||value.assignment_id!==item.id||!UUID.test(value.assignment_id)
    ||value.protocol_version!==item.protocol_version||value.status!=='unverified_draft'||value.label_origin!=='manual_independent_reader_unverified'
    ||['clinical_gate_authorized','training_release_authorized','reader_qualification_verified','reader_independence_verified'].some(k=>value[k]!==false)
    ||!exact(value.source,['case_id','source_sha256','shape','affine','units'])||!HASH.test(value.source.source_sha256)
    ||canonical(value.source)!==canonical(item.source)||!text(value.case_unavailable_reason,2000)
    ||!['not_assessed','lesions_proposed','no_lesion_reported','ungradable'].includes(value.case_disposition)
    ||['not_assessed','ungradable'].includes(value.case_disposition)&&!value.case_unavailable_reason.trim()
    ||!Array.isArray(value.lesions)||value.lesions.length>100
    ||value.case_disposition==='no_lesion_reported'&&value.lesions.length>0||value.case_disposition==='lesions_proposed'&&!value.lesions.length)fail();
  validateNativeGeometry(value.source);
  const ids=new Set(),keys=LESION_KEYS;
  for(const row of value.lesions){
    if(row.percentage_narrowing!==null||row.severity_category!==null)fail();
    if(!exact(row,keys)||!UUID.test(row.draft_id)||ids.has(row.draft_id)||!['','LM','LAD','LCx','RCA','graft','other'].includes(row.artery)
      ||!['segment','segment_convention'].every(k=>text(row[k],200))||!text(row.notes,1000)||!text(row.unavailable_reason,1000)||!row.unavailable_reason.trim()
      ||!['reference_selection','percentage_basis','measurement_method'].every(k=>text(row[k],500))||!text(row.measurement_evidence,2000)
      ||row.severity_category!==null&&!SEVERITY_CHOICES.includes(row.severity_category))fail();
    ids.add(row.draft_id);
    for(const key of POINT_FIELDS)if(row[key]!==null&&(!Array.isArray(row[key])||row[key].length!==3||!row[key].every((n,i)=>typeof n==='number'&&Number.isFinite(n)&&n>=0&&n<=value.source.shape[i]-1)))fail();
    for(const key of ['minimum_lumen_diameter_mm','adjacent_reference_diameter_mm','percentage_narrowing']){
      const n=row[key];if(n!==null&&(typeof n!=='number'||!Number.isFinite(n)||n<0||key==='adjacent_reference_diameter_mm'&&n===0||key==='percentage_narrowing'&&n>100))fail();
    }
    if(row.percentage_narrowing!==null&&!row.percentage_basis.trim()||row.adjacent_reference_diameter_mm!==null&&!row.reference_selection.trim())fail();
    if(row.minimum_lumen_diameter_mm!==null||row.adjacent_reference_diameter_mm!==null){
      if(!row.measurement_method.trim()||!row.measurement_evidence.trim())fail();
      if(row.minimum_lumen_diameter_mm!==null&&(!row.minimum_caliper_start_ijk||!row.minimum_caliper_end_ijk)
        ||row.adjacent_reference_diameter_mm!==null&&(!row.reference_caliper_start_ijk||!row.reference_caliper_end_ijk))fail();
    }
  }
  return value;
}
export function reviewAnnotationSnapshot(value,item){
  validateReviewAnnotation(value,item);const text=JSON.stringify(value);
  if(new TextEncoder().encode(text).byteLength>2*1024*1024)fail();
  const snapshot=JSON.parse(text);validateReviewAnnotation(snapshot,item);return snapshot;
}
export function reviewAnnotationBlob(value,item){const snapshot=reviewAnnotationSnapshot(value,item);return new Blob([JSON.stringify(snapshot,null,2)],{type:'application/json;charset=utf-8'});}
