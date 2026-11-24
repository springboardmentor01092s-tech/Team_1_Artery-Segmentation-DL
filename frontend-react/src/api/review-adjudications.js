import api from './client.js';
import {validateNativeGeometry} from '../lib/annotation-draft.js';
import {validateReviewAnnotation} from '../lib/review-annotation.js';
import {reviewCoverage} from '../lib/review-coverage.js';
const UUID=/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i,HASH=/^[a-f0-9]{64}$/;
export const canonical=v=>JSON.stringify(v,(_,x)=>x&&typeof x==='object'&&!Array.isArray(x)?Object.fromEntries(Object.keys(x).sort().map(k=>[k,x[k]])):x);
const path=id=>{if(!UUID.test(id))throw new Error('Invalid adjudication assignment');return `/review-adjudications/${id}`;};
const flags=v=>{if(v?.clinical_gate_authorized!==false||v.training_release_authorized!==false)throw new Error('Adjudication release authorization must remain false');};
const exact=(value,keys)=>value&&typeof value==='object'&&!Array.isArray(value)&&Object.keys(value).length===keys.length&&keys.every(k=>Object.hasOwn(value,k));
const reason=value=>typeof value==='string'&&value.trim()&&Array.from(value).length<=2000;
export function validateAdjudicationDocument(v,item){
  flags(v);
  if(!exact(v,['schema_version','assignment_id','source_sha256','protocol_version','r1_submission_sha256','r2_submission_sha256','outcome','reason','correspondences','resolutions','clinical_gate_authorized','training_release_authorized'])
    ||v.schema_version!=='review-adjudication/0.1'||v.assignment_id!==item.id||v.source_sha256!==item.source.source_sha256
    ||v.protocol_version!==item.protocol_version||v.r1_submission_sha256!==item.parents[0].record_sha256||v.r2_submission_sha256!==item.parents[1].record_sha256
    ||!['not_assessed','agreement','resolved_disagreement','unresolved'].includes(v.outcome)||!reason(v.reason)
    ||!Array.isArray(v.correspondences)||v.correspondences.length>200||!Array.isArray(v.resolutions)||v.resolutions.length>1200)
    throw new Error('Invalid source-bound adjudication document');
  const allowed=item.parents.map(p=>new Set(p.submission.document.lesions.map(v=>v.draft_id))),used=[new Set(),new Set()],ids=new Set(),decisions=new Set();
  for(const row of v.correspondences){
    if(!exact(row,['id','r1_lesion_ids','r2_lesion_ids','relation','reason'])||!UUID.test(row.id)||ids.has(row.id)||!reason(row.reason)
      ||!['matched','only_r1','only_r2','uncertain'].includes(row.relation))throw new Error('Invalid lesion correspondence');
    ids.add(row.id);
    for(let i=0;i<2;i++){
      const values=row[`r${i+1}_lesion_ids`];if(!Array.isArray(values)||values.length>100)throw new Error('Invalid parent lesion references');
      for(const id of values){if(!UUID.test(id)||!allowed[i].has(id)||used[i].has(id))throw new Error('Unknown or duplicated parent lesion');used[i].add(id);}
    }
    if(!row.r1_lesion_ids.length&&!row.r2_lesion_ids.length||row.relation==='matched'&&(!row.r1_lesion_ids.length||!row.r2_lesion_ids.length)
      ||row.relation==='only_r1'&&(!row.r1_lesion_ids.length||row.r2_lesion_ids.length)||row.relation==='only_r2'&&(!row.r2_lesion_ids.length||row.r1_lesion_ids.length))throw new Error('Correspondence contradicts its parent references');
  }
  for(const row of v.resolutions){
    const key=`${row.correspondence_id}:${row.field}`;
    if(!exact(row,['correspondence_id','field','decision','reason'])||!ids.has(row.correspondence_id)||decisions.has(key)||!reason(row.reason)
      ||!['lesion_presence','artery_segment','location_boundaries','minimum_diameter','reference_diameter','measurement_method'].includes(row.field)
      ||!['agreement','prefer_r1','prefer_r2','unresolved'].includes(row.decision))throw new Error('Invalid discrepancy decision');
    decisions.add(key);
  }
  return v;
}
export function validateAdjudicationDetail(v,id,owner){
  flags(v);validateNativeGeometry(v.source);
  if(v.id!==id||v.reviewer_id!==owner||v.case_id!==v.source.case_id||typeof v.source_current!=='boolean'||!HASH.test(v.source.source_sha256)
    ||!Array.isArray(v.parents)||v.parents.length!==2||!Array.isArray(v.history)||v.history.length>50)throw new Error('Adjudication source or owner mismatch');
  for(const parent of v.parents){
    const p=parent.submission;flags(p);
    if(!HASH.test(parent.record_sha256)||p.schema_version!=='independent-review-submission/0.1'||canonical(p.source)!==canonical(v.source)||p.protocol_version!==v.protocol_version)
      throw new Error('Frozen parent review provenance mismatch');
    validateReviewAnnotation(p.document,{id:p.assignment_id,source:v.source,protocol_version:v.protocol_version});
  }
  if(v.documentation_coverage!==undefined&&canonical(v.documentation_coverage)!==canonical(reviewCoverage(v)))throw new Error('Frozen review documentation coverage mismatch');
  const first=v.history_first_revision??1;
  if(!Number.isSafeInteger(first)||first<1||v.history_truncated!==undefined&&v.history_truncated!==(first>1))throw new Error('Invalid adjudication history range');
  let prior=first>1?v.history[0]?.previous_sha256:null;
  for(let i=0;i<v.history.length;i++){
    const row=v.history[i];
    if(row.revision!==i+first||!HASH.test(row.record_sha256)||row.previous_sha256!==prior||typeof row.final!=='boolean')throw new Error('Broken adjudication history');
    prior=row.record_sha256;
  }
  if(v.current){
    validateAdjudicationRecord(v.current,v,owner);
    if(v.current.record_sha256!==prior||v.current.record.revision!==v.history.length+first-1)throw new Error('Adjudication revision mismatch');
  }else if(v.history.length)throw new Error('Missing current adjudication');
  return structuredClone(v);
}
export function validateAdjudicationRecord(value,item,owner){
  const p=value?.record;flags(value.clinical_gate_authorized===undefined?item:value);flags(p);flags(p?.document);
  if(!p||!HASH.test(value.record_sha256)||!HASH.test(value.document_sha256)||p.schema_version!=='review-adjudication-version/0.1'||p.assignment_id!==item.id||p.reviewer_id!==owner
    ||!Number.isSafeInteger(p.revision)||p.revision<1||p.document.assignment_id!==item.id||p.document.source_sha256!==item.source.source_sha256
    ||p.document.protocol_version!==item.protocol_version||p.document.r1_submission_sha256!==item.parents[0].record_sha256
    ||p.document.r2_submission_sha256!==item.parents[1].record_sha256||!['unverified_adjudication_draft','adjudicated_unverified'].includes(p.status))
    throw new Error('Adjudication record provenance mismatch');
  validateAdjudicationDocument(p.document,item);
  return structuredClone(value);
}
export const adjudicationsApi={
  async list({signal}={}){const r=await api.get('/review-adjudications',{signal});flags(r.data);if(!Array.isArray(r.data.items))throw new Error('Invalid adjudication list');return r.data;},
  async catalogue({signal}={}){const r=await api.get('/review-adjudication-catalogue',{signal});flags(r.data);if(!Array.isArray(r.data.studies)||!Array.isArray(r.data.credentials))throw new Error('Invalid coordinator catalogue');return r.data;},
  async assign(study,credential,{signal}={}){const r=await api.post(`/review-studies/${study.id}/adjudicator`,{reviewer_id:credential.reviewer_id,credential_id:credential.id,expected_source_sha256:study.source_sha256},{signal});flags(r.data);return r.data;},
  async detail(id,owner,{signal}={}){const r=await api.get(path(id),{signal,timeout:60000});return validateAdjudicationDetail(r.data,id,owner);},
  async version(item,owner,revision,{signal}={}){
    if(!Number.isSafeInteger(revision)||revision<1||revision>2147483647)throw new Error('Invalid adjudication revision');
    const r=await api.get(path(item.id)+`/versions/${revision}`,{signal,timeout:60000}),v=validateAdjudicationRecord(r.data,item,owner);
    if(v.record.revision!==revision)throw new Error('Historical revision mismatch');return v;
  },
  async loadOriginalCt(item,owner,{signal,onProgress}={}){
    const controller=new AbortController(),cancel=()=>controller.abort();let exceeded=false;
    const token=localStorage.getItem('vascuai_token');
    const current=()=>{if(!token||token!==localStorage.getItem('vascuai_token')||controller.signal.aborted)throw new Error('Original CT session changed or cancelled');};
    signal?.addEventListener('abort',cancel,{once:true});if(signal?.aborted)cancel();
    try{
      current();
      const before=await this.detail(item.id,owner,{signal:controller.signal});
      current();
      if(!before.source_current||canonical(before.source)!==canonical(item.source))throw new Error('Original CT changed');
      const r=await api.get(path(item.id)+'/source',{responseType:'arraybuffer',signal:controller.signal,timeout:120000,onDownloadProgress:event=>{
        if(event.loaded>512*1024*1024||event.total>512*1024*1024){exceeded=true;controller.abort();}
        if(!controller.signal.aborted)onProgress?.(event);
      }});
      if(r.status!==200||!(r.data instanceof ArrayBuffer)||!r.data.byteLength||r.data.byteLength>512*1024*1024||/json|html|text\//i.test(r.headers?.['content-type']||''))throw new Error('Original CT response invalid');
      const hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',r.data)),b=>b.toString(16).padStart(2,'0')).join('');
      current();
      if(hash!==item.source.source_sha256||controller.signal.aborted)throw new Error('Original CT checksum mismatch or cancelled request');
      const after=await this.detail(item.id,owner,{signal:controller.signal});
      current();
      if(!after.source_current||canonical(after.source)!==canonical(item.source))throw new Error('Original CT changed during download');
      return r.data;
    }catch(error){if(exceeded)throw new Error('Original CT exceeds the 512 MiB browser transfer limit');throw error;}
    finally{signal?.removeEventListener('abort',cancel);}
  },
  async download(item,owner,options={}){
    const buffer=await this.loadOriginalCt(item,owner,options),bytes=new Uint8Array(buffer),gzip=bytes[0]===31&&bytes[1]===139;
    return {blob:new Blob([buffer],{type:'application/octet-stream'}),filename:`original-ct-${item.case_id}.nii${gzip?'.gz':''}`};
  },
  async save(item,owner,document,revision,{signal}={}){
    let snapshot;
    try{snapshot=JSON.parse(JSON.stringify(document));validateAdjudicationDocument(snapshot,item);}
    catch(error){error.localValidation=true;throw error;}
    const r=await api.put(path(item.id)+'/draft',{document:snapshot,expected_revision:revision},{signal,timeout:60000});
    const v=validateAdjudicationRecord(r.data,item,owner);
    if(v.record.revision!==revision+1||canonical(v.record.document)!==canonical(snapshot))throw new Error('Adjudication save not confirmed');return v;
  },
  async submit(item,owner,record,{signal}={}){
    // Return the server's saved hash as a concurrency check; the server verifies
    // its stored bytes again. Avoid incompatible JavaScript/Python number and
    // Unicode canonicalization at this boundary.
    if(!HASH.test(record.document_sha256))throw new Error('Saved document hash unavailable');
    const r=await api.post(path(item.id)+'/submit',{expected_revision:record.record.revision,expected_document_sha256:record.document_sha256,acknowledge_unverified:true},{signal,timeout:60000});
    return validateAdjudicationRecord(r.data,item,owner);
  },
};
