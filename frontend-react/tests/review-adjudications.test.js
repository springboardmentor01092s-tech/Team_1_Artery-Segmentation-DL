import test from 'node:test';
import assert from 'node:assert/strict';
import {validateAdjudicationDetail,validateAdjudicationRecord} from '../src/api/review-adjudications.js';
import {newReviewAnnotation} from '../src/lib/review-annotation.js';
import {loadAdjudicationCt} from '../src/lib/adjudication-ct-loader.js';
import {reviewCoverage} from '../src/lib/review-coverage.js';
import {syntheticNifti} from './e2e/nifti-fixture.js';
import {verifyOriginalCt} from '../src/lib/ct-review-volume.js';
import {inspectVolume} from '../src/lib/volume-geometry.js';
import {createHash} from 'node:crypto';
import {reportJsonBlob,downloadRecords} from '../src/lib/exports.js';
const id='11111111-1111-4111-8111-111111111111',reviewId='22222222-2222-4222-8222-222222222222';
export function adjudicationFixture(){
  const source={case_id:1,source_sha256:'a'.repeat(64),shape:[12,10,8],affine:[[1,0,0,0],[0,2,0,0],[0,0,3,0],[0,0,0,1]],units:'mm'};
  const flags={clinical_gate_authorized:false,training_release_authorized:false};
  const item={id,reviewer_id:3,case_id:1,source,protocol_version:'synthetic-unapproved',source_current:true,current:null,history:[],...flags};
  item.parents=[1,2].map(n=>({record_sha256:String(n).repeat(64),submission:{schema_version:'independent-review-submission/0.1',assignment_id:reviewId,
    reviewer_id:n,source,protocol_version:item.protocol_version,document:newReviewAnnotation({id:reviewId,source,protocol_version:item.protocol_version}),...flags}}));
  return item;
}
function saved(item){return {record_sha256:'c'.repeat(64),document_sha256:'d'.repeat(64),record:{schema_version:'review-adjudication-version/0.1',assignment_id:id,
  reviewer_id:3,revision:1,status:'unverified_adjudication_draft',clinical_gate_authorized:false,training_release_authorized:false,document:{
    schema_version:'review-adjudication/0.1',assignment_id:id,source_sha256:item.source.source_sha256,protocol_version:item.protocol_version,
    r1_submission_sha256:item.parents[0].record_sha256,r2_submission_sha256:item.parents[1].record_sha256,
    outcome:'not_assessed',reason:'Synthetic unassessed test',correspondences:[],resolutions:[],clinical_gate_authorized:false,training_release_authorized:false}}};}
test('adjudication adapter accepts detached owner/source-bound unverified reviews',()=>{
  const item=adjudicationFixture();const result=validateAdjudicationDetail(item,id,3);assert.deepEqual(result,item);assert.notEqual(result,item);
});
for(const [name,change] of [
  ['owner',v=>v.reviewer_id=4],['source',v=>v.parents[0].submission.source={...v.source,source_sha256:'b'.repeat(64)}],
  ['singular geometry',v=>v.source.affine[0]=[0,0,0,0]],['clinical release',v=>v.clinical_gate_authorized=true],
  ['training release',v=>v.training_release_authorized=true],['parent hash',v=>v.parents[1].record_sha256='bad'],
  ['foreign worksheet',v=>v.parents[0].submission.document.assignment_id=id],
  ['broken history',v=>v.history=[{revision:2,record_sha256:'c'.repeat(64),previous_sha256:null,final:false}]],
])test(`adjudication adapter rejects ${name}`,()=>{const item=adjudicationFixture();change(item);assert.throws(()=>validateAdjudicationDetail(item,id,3));});
test('saved adjudication requires source and both original parent hashes',()=>{
  const item=adjudicationFixture(),value=saved(item);assert.deepEqual(validateAdjudicationRecord(value,item,3),value);
  const before=structuredClone(value);value.record.document.r2_submission_sha256='f'.repeat(64);
  assert.throws(()=>validateAdjudicationRecord(value,item,3));assert.equal(before.record.document.r2_submission_sha256,'2'.repeat(64));
});

for(const [name,change] of [
  ['missing correspondences',v=>delete v.correspondences],['non-array decisions',v=>v.resolutions={}],
  ['unknown field',v=>v.percentage_narrowing=37],['invalid outcome',v=>v.outcome='clinically_approved'],
  ['absent decision reason',v=>v.reason=''],
])test(`saved adjudication rejects ${name} before UI use`,()=>{
  const item=adjudicationFixture(),value=saved(item);change(value.record.document);assert.throws(()=>validateAdjudicationRecord(value,item,3));
});
test('bounded recent history retains a source-bound current revision beyond the first page',()=>{
  const item=adjudicationFixture();item.current=saved(item);item.current.record.revision=51;
  item.history_first_revision=50;item.history_truncated=true;
  item.history=[{revision:50,record_sha256:'e'.repeat(64),previous_sha256:'f'.repeat(64),final:false},
    {revision:51,record_sha256:'c'.repeat(64),previous_sha256:'e'.repeat(64),final:false}];
  assert.deepEqual(validateAdjudicationDetail(item,id,3),item);
});

test('documentation counts preserve unassessed empty reviews instead of claiming normality',()=>{
  const item=adjudicationFixture(),value=reviewCoverage(item);
  assert.equal(value.readers.length,2);assert.equal(value.readers[0].case_disposition,'not_assessed');
  assert.equal(value.readers[0].landmark_fields,0);assert.equal(value.readers[0].recorded_lesion_rows,0);
  assert.equal(value.evidence_receipts_status,'not_verified');assert.equal(value.protocol_signoff_status,'not_verified');
  item.documentation_coverage=value;validateAdjudicationDetail(item,item.id,3);
  item.documentation_coverage.readers[0].recorded_lesion_rows=4;assert.throws(()=>validateAdjudicationDetail(item,item.id,3),/coverage mismatch/);
});

for(const schema_version of ['review-documentation-coverage/0.1','automatic-branch-evidence/0.1','experimental-branch-graph/0.1'])test(`separate evidence is refused by both normal exports: ${schema_version}`,()=>{
  const value={schema_version,clinical_gate_authorized:false,training_release_authorized:false};
  assert.throws(()=>reportJsonBlob({result:{nested:value}}));
  assert.throws(()=>downloadRecords([{id:1,notes:{nested:value}}],'json'));
});

function ctEnvironment(t,hold=false){
  let token='synthetic-session';const originals=new Map(),workers=[];
  const globals={isSecureContext:true,localStorage:{getItem:()=>token},Worker:class{
    constructor(){workers.push(this);}terminate(){this.terminated=true;}
    postMessage(message){this.release=async()=>{try{this.onmessage({data:await verifyOriginalCt(message.ct,message.source)});}catch(e){this.onmessage({data:{error:e.message}});}};if(!hold)queueMicrotask(this.release);}
  }};
  for(const [k,v]of Object.entries(globals)){originals.set(k,Object.getOwnPropertyDescriptor(globalThis,k));Object.defineProperty(globalThis,k,{configurable:true,value:v});}
  t.after(()=>{for(const [k,v]of originals){if(v)Object.defineProperty(globalThis,k,v);else delete globalThis[k];}});
  const ct=syntheticNifti().buffer,g=inspectVolume(ct),item=adjudicationFixture();
  item.source={case_id:1,source_sha256:createHash('sha256').update(new Uint8Array(ct)).digest('hex'),shape:g.shape,affine:g.affine,units:'mm'};
  for(const parent of item.parents){parent.submission.source=structuredClone(item.source);parent.submission.document.source=structuredClone(item.source);}
  return {item,ct,workers,changeSession:()=>{token='new-session';}};
}

test('third-reader CT loader checks actual checksum/geometry and pre/post parent/source identity',async t=>{
  const f=ctEnvironment(t),calls=[],api={detail:async()=>{calls.push('detail');return structuredClone(f.item);},loadOriginalCt:async()=>{calls.push('original');return f.ct;}};
  const value=await loadAdjudicationCt(api,f.item,3,{signal:new AbortController().signal});
  assert.deepEqual(calls,['detail','original','detail']);assert.deepEqual(value.geometry.shape,f.item.source.shape);assert.ok(f.workers[0].terminated);
});

for(const kind of ['owner','geometry','clinical','source','parent'])test(`third-reader CT refuses mismatched ${kind}`,async t=>{
  const f=ctEnvironment(t);let downloads=0;
  const api={detail:async()=>{const value=structuredClone(f.item);
    if(kind==='owner')value.reviewer_id++;
    if(kind==='geometry')value.source.affine[0]=[0,0,0,0];
    if(kind==='clinical')value.clinical_gate_authorized=true;
    if(kind==='source')value.source_current=false;
    if(kind==='parent')value.parents[0].record_sha256='f'.repeat(64);
    return value;},loadOriginalCt:async()=>{downloads++;return f.ct;}};
  await assert.rejects(loadAdjudicationCt(api,f.item,3,{signal:new AbortController().signal}));assert.equal(downloads,0);
});

test('third-reader CT download cannot complete into a new token session',async t=>{
  const f=ctEnvironment(t),api={detail:async()=>structuredClone(f.item),loadOriginalCt:async()=>{f.changeSession();return f.ct;}};
  await assert.rejects(loadAdjudicationCt(api,f.item,3,{signal:new AbortController().signal}),/session changed/);assert.equal(f.workers.length,0);
});

test('cancelled third-reader decoder is terminated and cannot publish stale CT',async t=>{
  const f=ctEnvironment(t,true),controller=new AbortController(),api={detail:async()=>structuredClone(f.item),loadOriginalCt:async()=>f.ct};
  const pending=loadAdjudicationCt(api,f.item,3,{signal:controller.signal});
  while(!f.workers.length)await new Promise(r=>setTimeout(r,1));controller.abort();
  await assert.rejects(pending,/cancelled/);assert.ok(f.workers[0].terminated);
});
