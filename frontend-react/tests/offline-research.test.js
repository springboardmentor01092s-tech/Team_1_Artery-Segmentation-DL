import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createOfflineResearchApi,parseOfflineEvidence,checkedOfflineReceipt,hashOfflineText,MAX_OFFLINE_BYTES} from '../src/api/offline-research-contract.js';
import {createOfflineResearchAssessment} from '../src/lib/research-assessment.js';
import {downloadRecords,reportJsonBlob} from '../src/lib/exports.js';

export const offlineEnvelope=JSON.parse(readFileSync(new URL('./fixtures/offline-research-synthetic.json',import.meta.url),'utf8'));
export const offlineText=JSON.stringify(offlineEnvelope);
const p=offlineEnvelope.record.profile;
export const offlineResult={id:p.source.parent_segmentation_result_id,case_id:1,stale:false,metadata:{source_sha256:p.source.source_sha256,shape:p.geometry.shape,affine:p.geometry.affine,xyzt_units:2}};
export async function responseFor(text=offlineText,result=offlineResult){
  const e=JSON.parse(text);
  return {schema_version:'verified-offline-research/0.1',procedure_version:'0.1',case_id:result.case_id,segmentation_result_id:result.id,
    evidence_sha256:await hashOfflineText(text),verified_at:'2026-11-24T10:00:00Z',profile:e.record.profile,source_files:e.record.source_files,
    implementation_sha256:e.record.implementation_sha256,segmentation:structuredClone(result),
    verification_scope:'recomputed_against_current_stored_files_not_clinical_attestation',clinical_gate_authorized:false,training_release_authorized:false};
}

test('authenticated verification is exact request-bound, immutable and replayable without loading mask',async()=>{
  const calls=[];
  const api=createOfflineResearchApi({post:async(url,text,config)=>{calls.push({url,text,config});return {status:200,data:await responseFor(text)};}},{getSession:()=> 'test-session'});
  const receipt=await api.verify(offlineResult,offlineText),value=await createOfflineResearchAssessment(receipt,offlineResult);
  assert.equal(calls.length,1);assert.equal(calls[0].text,offlineText);assert.match(calls[0].url,/research-evidence\/verify$/);
  assert.ok(Object.isFrozen(receipt.profile));assert.equal(value.document.clinical_gate_authorized,false);
  assert.equal(value.document.training_release_authorized,false);assert.equal(value.document.records.length,3);
  assert.equal((await createOfflineResearchAssessment(receipt,offlineResult)).sha256,value.sha256);
  assert.throws(()=>checkedOfflineReceipt(structuredClone(receipt),offlineResult),/Fresh source/);
  assert.throws(()=>checkedOfflineReceipt(receipt,{...offlineResult,id:'different'}),/Fresh source/);
});

for(const [name,mutate]of Object.entries({
  authorization:v=>{v.clinical_gate_authorized=true;},training:v=>{v.training_release_authorized=true;},
  source:v=>{v.profile.source.source_sha256='f'.repeat(64);},geometry:v=>{v.profile.geometry.affine[0][3]+=1;},
  coordinate:v=>{v.profile.branches[0].sections[0].sample_ijk[0]+=1;},implementation:v=>{v.implementation_sha256.sampler='f'.repeat(64);},
  context:v=>{v.segmentation.metadata.shape[0]++;},request:v=>{v.evidence_sha256='f'.repeat(64);},
  procedure:v=>{v.procedure_version='forged';},case:v=>{v.case_id++;}
}))test(`altered response rejected: ${name}`,async()=>{
  const api=createOfflineResearchApi({post:async()=>{const data=await responseFor();mutate(data);return {status:200,data};}},{getSession:()=> 'test-session'});
  await assert.rejects(api.verify(offlineResult,offlineText));
});

test('incomplete, oversized, wrong-version and elevated evidence fail before transport',async()=>{
  let count=0;const api=createOfflineResearchApi({post:()=>{count++;throw Error('must not send');}},{getSession:()=> 'test-session'});
  for(const text of ['{}','x'.repeat(MAX_OFFLINE_BYTES+1),JSON.stringify({...offlineEnvelope,schema_version:'future'}),JSON.stringify({...offlineEnvelope,record:{...offlineEnvelope.record,training_release_authorized:true}})])await assert.rejects(api.verify(offlineResult,text));
  assert.equal(count,0);assert.throws(()=>parseOfflineEvidence('null'));
});

test('pending response and previous receipt cannot cross session changes',async()=>{
  let token='first',release;
  const api=createOfflineResearchApi({post:async()=>{await new Promise(r=>{release=r;});return {status:200,data:await responseFor()};}},{getSession:()=>token});
  const pending=api.verify(offlineResult,offlineText);while(!release)await new Promise(r=>setTimeout(r,1));token='second';release();
  await assert.rejects(pending,/Session\/source changed/);
  token='first';const immediate=createOfflineResearchApi({post:async()=>({status:200,data:await responseFor()})},{getSession:()=>token});
  const receipt=await immediate.verify(offlineResult,offlineText);token='second';assert.throws(()=>checkedOfflineReceipt(receipt,offlineResult),/Fresh source/);
});

test('all offline wrappers are refused by both public normal JSON exports',()=>{
  for(const schema_version of ['offline-research-evidence/0.1','offline-research-workspace/0.1','verified-offline-research/0.1']){
    const value={nested:[{schema_version,clinical_gate_authorized:false}]};
    assert.throws(()=>reportJsonBlob({result:value}),/research/i);
    assert.throws(()=>downloadRecords([{id:1,notes:value}],'json'),/research/i);
  }
});

test('lightweight identity remains authenticated and rejects a forged or changed source response',async()=>{
  const identity={schema_version:'offline-research-source/0.1',case_id:1,segmentation_result_id:offlineResult.id,
    mask_file_sha256:offlineEnvelope.record.source_files.mask_file_sha256,segmentation:structuredClone(offlineResult),clinical_gate_authorized:false,training_release_authorized:false};
  let token='first';const api=createOfflineResearchApi({get:async()=>({status:200,data:structuredClone(identity)})},{getSession:()=>token});
  assert.equal((await api.identity(offlineResult)).mask_file_sha256,identity.mask_file_sha256);
  identity.segmentation.metadata.source_sha256='f'.repeat(64);await assert.rejects(api.identity(offlineResult));
  token=null;await assert.rejects(api.identity(offlineResult));
});
