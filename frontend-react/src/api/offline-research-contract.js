import {isHash,isUUID,geometryFingerprint} from '../lib/stenosis-results.js';
import {validateNativeGeometry} from '../lib/annotation-draft.js';

export const MAX_OFFLINE_BYTES=2*1024*1024;
const receipts=new WeakMap();
const fail=message=>{throw new Error(message);};
const sort=value=>Array.isArray(value)?value.map(sort):value&&typeof value==='object'?Object.fromEntries(Object.keys(value).sort().map(k=>[k,sort(value[k])])):value;
const same=(a,b)=>JSON.stringify(sort(a))===JSON.stringify(sort(b));
const freeze=value=>{if(value&&typeof value==='object'){Object.values(value).forEach(freeze);Object.freeze(value);}return value;};
const metaKeys=['source_sha256','shape','affine','xyzt_units','checkpoint_sha256','threshold','architecture','model_name','model_version','recipe'];
export const offlineBinding=result=>JSON.stringify([result?.id,result?.case_id,result?.stale,...metaKeys.map(k=>result?.metadata?.[k]??null)]);
export const hashOfflineText=async text=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(text))),n=>n.toString(16).padStart(2,'0')).join('');

export function parseOfflineEvidence(text){
  if(typeof text!=='string'||!text.length||new TextEncoder().encode(text).length>MAX_OFFLINE_BYTES)fail('Offline evidence must be nonempty and at most 2 MiB.');
  const value=JSON.parse(text);
  if(!value||Object.keys(value).sort().join(',')!=='plan_json,record,schema_version'||value.schema_version!=='offline-research-evidence/0.1'||typeof value.plan_json!=='string'
    ||value.record?.schema_version!=='full-volume-research-profile/0.1'||value.record.clinical_gate_authorized!==false||value.record.training_release_authorized!==false)fail('Unsupported or unsafe offline evidence format.');
  return value;
}

function checkCoordinates(ijk,world,g){
  if(!Array.isArray(ijk)||ijk.length!==3||ijk.some((n,i)=>!Number.isFinite(n)||n< -1e-6||n>g.shape[i]-1+1e-6)
    ||!Array.isArray(world)||world.length!==3||world.some(n=>!Number.isFinite(n)))fail('Invalid offline coordinates.');
  const expected=g.affine.slice(0,3).map(row=>row[3]+row.slice(0,3).reduce((sum,n,i)=>sum+n*ijk[i],0));
  if(expected.some((n,i)=>Math.abs(n-world[i])>1e-5+Math.abs(n)*1e-6))fail('Offline IJK/RAS mismatch.');
}

async function checkResponse(value,envelope,result,requestHash){
  if(!value||value.schema_version!=='verified-offline-research/0.1'||value.procedure_version!=='0.1'||value.clinical_gate_authorized!==false||value.training_release_authorized!==false
    ||value.case_id!==result.case_id||value.segmentation_result_id!==result.id||value.evidence_sha256!==requestHash
    ||value.verification_scope!=='recomputed_against_current_stored_files_not_clinical_attestation'||!Number.isFinite(Date.parse(value.verified_at)))fail('Unexpected offline verification response.');
  if(offlineBinding(value.segmentation)!==offlineBinding(result))fail('Saved model/source changed. Refresh history.');
  if(!same(value.profile,envelope.record.profile)||!same(value.source_files,envelope.record.source_files)||!same(value.implementation_sha256,envelope.record.implementation_sha256))fail('Verification does not describe the imported evidence.');
  if(Object.keys(value.implementation_sha256).sort().join(',')!=='orchestrator,sampler,storage'||Object.values(value.implementation_sha256).some(v=>!isHash(v)))fail('Missing implementation provenance.');
  const p=value.profile,g=p.geometry;
  validateNativeGeometry({...g,units:g.world_unit});
  if(p.schema_version!=='experimental-candidates/1.0'||p.algorithm?.id!=='experimental-mask-profile'||p.algorithm.version!=='0.1.0'
    ||p.source?.mask_role!=='model_prediction'||p.source.parent_segmentation_result_id!==result.id||p.source.source_sha256!==result.metadata.source_sha256
    ||!same(g.shape,result.metadata.shape)||!same(g.affine,result.metadata.affine)||!isHash(p.source.mask_sha256)
    ||value.source_files.ct_sha256!==p.source.source_sha256||!isHash(value.source_files.mask_file_sha256)||!isHash(p.parameters_sha256)||!isHash(p.branch_geometry_sha256)
    ||p.source.geometry_fingerprint!==await geometryFingerprint(g,p.source.source_sha256))fail('Offline source/geometry binding mismatch.');
  if(!Array.isArray(p.branches)||p.branches.length>8||!Array.isArray(p.candidates)||p.candidates.length>128)fail('Offline evidence resource limit.');
  const ids=new Set();let count=0;
  for(const branch of p.branches){
    if(typeof branch.branch_id!=='string'||ids.has(branch.branch_id)||!Array.isArray(branch.sections)||branch.sections.length<2||branch.sections.length>512)fail('Invalid offline branch evidence.');
    ids.add(branch.branch_id);count+=branch.sections.length;
    for(const [i,row] of branch.sections.entries()){
      checkCoordinates(row.sample_ijk,row.world_ras_mm,g);
      if(!Number.isFinite(row.s_mm)||Math.abs(row.s_mm-i*p.parameters.sample_step_mm)>1e-6||!['abstained','evaluable_candidate_only'].includes(row.status)
        ||row.diagnostic_area_mm2!==null&&(!Number.isFinite(row.diagnostic_area_mm2)||row.diagnostic_area_mm2<=0))fail('Invalid offline sample reference.');
    }
  }
  if(count>2048)fail('Offline section limit.');
  for(const candidate of p.candidates){checkCoordinates(candidate.sample_ijk,candidate.world_ras_mm,g);if(!ids.has(candidate.branch_id))fail('Unknown candidate branch.');}
  return value;
}

export function createOfflineResearchApi(api,{getSession=()=>localStorage.getItem('vascuai_token')}={}){
  return {
  async identity(result,{signal}={}){
    if(!Number.isSafeInteger(result?.case_id)||result.case_id<1||!isUUID(result.id)||result.stale!==false)fail('Select a current saved segmentation.');
    const token=getSession(),binding=offlineBinding(result);if(!token||signal?.aborted)fail('Research source session changed.');
    const r=await api.get(`/cases/${result.case_id}/segmentations/${result.id}/research-evidence/identity`,{signal,timeout:60000}),v=r.data;
    if(r.status!==200||!v||v.schema_version!=='offline-research-source/0.1'||v.case_id!==result.case_id||v.segmentation_result_id!==result.id
      ||v.clinical_gate_authorized!==false||v.training_release_authorized!==false||!isHash(v.mask_file_sha256)
      ||offlineBinding(v.segmentation)!==binding||token!==getSession()||signal?.aborted)fail('Research source identity or session changed.');
    return v;
  },
  async verify(result,text,{signal}={}){
    if(!Number.isSafeInteger(result?.case_id)||result.case_id<1||!isUUID(result.id)||result.stale!==false)fail('Select a current saved segmentation.');
    const envelope=parseOfflineEvidence(text),binding=offlineBinding(result),token=getSession();
    if(!token||signal?.aborted)fail('Session changed; no offline evidence accepted.');
    const hash=await hashOfflineText(text);
    if(token!==getSession()||signal?.aborted)fail('Session changed; no offline evidence accepted.');
    const response=await api.post(`/cases/${result.case_id}/segmentations/${result.id}/research-evidence/verify`,text,{headers:{'Content-Type':'application/json'},signal,timeout:0});
    if(response.status!==200)fail('The server did not verify the offline evidence.');
    const value=await checkResponse(structuredClone(response.data),envelope,result,hash);
    if(token!==getSession()||signal?.aborted||offlineBinding(result)!==binding)fail('Session/source changed; no offline evidence accepted.');
    freeze(value);receipts.set(value,{binding,token,getSession,text});return value;
  }};
}

// Only a fresh authenticated transport result can enter the shared assessment
// constructor. A restored JSON object with verified=true is never marked here.
export function checkedOfflineReceipt(receipt,result){
  const context=receipts.get(receipt);
  if(!context||context.binding!==offlineBinding(result)||context.token!==context.getSession())fail('Fresh source verification is required for offline research evidence.');
  return {profile:structuredClone(receipt.profile),segmentation:structuredClone(receipt.segmentation)};
}
