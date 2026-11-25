import api from './client.js';
import {reviewAnnotationSnapshot,validateReviewAnnotation} from '../lib/review-annotation.js';
const UUID=/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i;
const canonical=v=>JSON.stringify(v,(_,x)=>x&&typeof x==='object'&&!Array.isArray(x)?Object.fromEntries(Object.keys(x).sort().map(k=>[k,x[k]])):x);
function path(item){if(!UUID.test(item.id))throw new Error('Invalid assignment');return `/review-assignments/${item.id}/annotation-draft`;}
export function validateReaderDraft(value,item,ownerId){
  if(value?.assignment_id!==item.id||value.owner_id!==ownerId||value.case_id!==item.case_id||value.protocol_version!==item.protocol_version
    ||canonical(value.source)!==canonical(item.source)||canonical(value.geometry_identity)!==canonical(item.geometry_identity)
    ||!Number.isSafeInteger(value.revision)||value.revision<0||typeof value.exists!=='boolean'||value.exists!==(value.revision>0)
    ||value.status!=='unverified_draft'||typeof value.source_current!=='boolean'
    ||typeof value.submitted!=='boolean'
    ||['clinical_gate_authorized','training_release_authorized','reader_independence_verified','qualification_verified'].some(k=>value[k]!==false)
    ||value.exists&&(!/^[a-f0-9]{64}$/.test(value.content_sha256)||!value.document)||!value.exists&&(value.document!==null||value.content_sha256!==null))throw new Error('Unverified annotation response did not match this reader/source');
  if(value.document)validateReviewAnnotation(value.document,item);
  return structuredClone(value);
}
function validateAmendmentEntry(row,item,ownerId,parentHash,revision,previousHash){
  const p=row?.amendment;
  if(!row||!p||row.revision!==revision||row.previous_sha256!==previousHash||row.parent_submission_sha256!==parentHash
    ||!/^[a-f0-9-]{36}$/i.test(row.id)||!/^[a-f0-9]{64}$/.test(row.record_sha256)||!/^[a-f0-9]{64}$/.test(row.document_sha256)
    ||p.schema_version!=='review-submission-amendment/0.1'||p.id!==row.id||p.assignment_id!==item.id||p.reviewer_id!==ownerId
    ||p.revision!==revision||p.parent_submission_sha256!==parentHash||p.document_sha256!==row.document_sha256
    ||p.previous_sha256!==previousHash||p.previous_id!==(row.previous_id??null)
    ||p.status!=='unverified_addendum_original_submission_unchanged'
    ||p.clinical_gate_authorized!==false||p.training_release_authorized!==false
    ||canonical(p.source)!==canonical(item.source)||p.protocol_version!==item.protocol_version
    ||p.geometry_identity?.sha256!==item.geometry_identity.sha256)throw new Error('Amendment does not match this immutable submission/source');
  validateReviewAnnotation(p.document,item);
  // The API recomputes Python's canonical JSON hashes before returning records.
  // The browser validates the complete binding/chain fields without reserializing
  // JSON numbers, whose 1 versus 1.0 representation differs across runtimes.
  return structuredClone(row);
}
export const reviewAnnotationsApi={
  async read(item,ownerId,{signal}={}){const r=await api.get(path(item),{signal,timeout:60000});if(r.status!==200)throw new Error('Draft load not confirmed');return validateReaderDraft(r.data,item,ownerId);},
  async save(item,ownerId,document,revision,{signal}={}){
    const snapshot=reviewAnnotationSnapshot(document,item);
    if(!Number.isSafeInteger(revision)||revision<0||revision>=2147483647)throw new Error('Invalid draft revision');
    const r=await api.put(path(item),{document:snapshot,expected_revision:revision},{signal,timeout:60000});
    const v=validateReaderDraft(r.data,item,ownerId);
    if(r.status!==(revision===0?201:200)||v.revision!==revision+1||canonical(v.document)!==canonical(snapshot)||!v.source_current)throw new Error('Draft save was not confirmed');
    return v;
  },
  async submit(item,ownerId,revision,documentSha256,{signal}={}){
    if(!Number.isSafeInteger(revision)||revision<1||!/^[a-f0-9]{64}$/.test(documentSha256))throw new Error('Save a verified draft revision before submission');
    const r=await api.post(path(item).replace(/annotation-draft$/,'submit'),{expected_revision:revision,expected_document_sha256:documentSha256,acknowledge_unverified:true},{signal,timeout:60000});
    const value=r.data,p=value?.submission;
    if(![200,201].includes(r.status)||!p||p.schema_version!=='independent-review-submission/0.1'||p.assignment_id!==item.id||p.reviewer_id!==ownerId
      ||p.annotation_revision!==revision||p.document_sha256!==documentSha256||!/^[a-f0-9]{64}$/.test(value.record_sha256)
      ||['clinical_gate_authorized','training_release_authorized'].some(k=>value[k]!==false||p[k]!==false))throw new Error('Immutable submission was not verified');
    validateReviewAnnotation(p.document,item);return structuredClone(value);
  },
  async submission(item,ownerId,{signal}={}){
    const r=await api.get(path(item).replace(/annotation-draft$/,'submission'),{signal,timeout:60000}),v=r.data,p=v?.submission;
    if(r.status!==200||v.exists!==true||!p||p.assignment_id!==item.id||p.reviewer_id!==ownerId
      ||p.schema_version!=='independent-review-submission/0.1'||!/^[a-f0-9]{64}$/.test(v.record_sha256)
      ||p.clinical_gate_authorized!==false||p.training_release_authorized!==false||v.clinical_gate_authorized!==false||v.training_release_authorized!==false)
      throw new Error('Immutable submission did not match this reader');
    validateReviewAnnotation(p.document,item);return structuredClone(v);
  },
  async amendments(item,ownerId,{signal}={}){
    const r=await api.get(path(item).replace(/annotation-draft$/,'amendments'),{signal,timeout:60000}),v=r.data;
    if(r.status!==200||v?.schema_version!=='review-amendment-history/0.1'||v.assignment_id!==item.id
      ||!/^[a-f0-9]{64}$/.test(v.submission_sha256)||!Number.isSafeInteger(v.revision)||v.revision<0||v.revision>100
      ||v.max_amendments!==100||v.clinical_gate_authorized!==false||v.training_release_authorized!==false
      ||typeof v.source_current!=='boolean'||!Array.isArray(v.items)||v.items.length!==v.revision)throw new Error('Amendment history was not verified');
    let previousHash=null,previousId=null;const items=[];
    for(let i=0;i<v.items.length;i++){
      const row=validateAmendmentEntry(v.items[i],item,ownerId,v.submission_sha256,i+1,previousHash);
      if(row.previous_id!==(previousId??null))throw new Error('Amendment chain is broken');
      items.push(row);previousHash=row.record_sha256;previousId=row.id;
    }
    if(v.latest_sha256!==(previousHash??null))throw new Error('Amendment head does not match its verified chain');
    return structuredClone({...v,items});
  },
  async appendAmendment(item,ownerId,submissionHash,document,reason,history,{signal}={}){
    if(!/^[a-f0-9]{64}$/.test(submissionHash)||typeof reason!=='string'||!reason.trim()||reason.length>2000
      ||!Number.isSafeInteger(history?.revision)||history.revision<0||history.revision>=100)throw new Error('Invalid amendment request');
    const snapshot=reviewAnnotationSnapshot(document,item),body={document:snapshot,reason:reason.trim(),expected_revision:history.revision,
      expected_previous_sha256:history.latest_sha256,expected_submission_sha256:submissionHash,acknowledge_unverified:true};
    const r=await api.post(path(item).replace(/annotation-draft$/,'amendments'),body,{signal,timeout:60000});
    if(r.status!==201)throw new Error('Amendment was not saved as a new immutable version');
    const row=validateAmendmentEntry(r.data,item,ownerId,submissionHash,history.revision+1,history.latest_sha256);
    if(row.amendment.reason!==body.reason||row.amendment.clinical_gate_authorized!==false||row.amendment.training_release_authorized!==false)throw new Error('Saved amendment response did not match the request');
    return row;
  },
};
