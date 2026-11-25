import test from 'node:test';
import assert from 'node:assert/strict';
import {webcrypto} from 'node:crypto';
import {createReviewAssignmentsApi,validateReviewAssignment,validateReviewNote,reviewBinding} from '../src/api/review-assignments-contract.js';
const flags={clinical_gate_authorized:false,training_release_authorized:false,reader_independence_verified:false,qualification_verified:false};
const item=()=>({id:'11111111-1111-4111-8111-111111111111',reviewer_id:7,slot:'R1',case_id:9,protocol_version:'synthetic-unapproved',
  source:{case_id:9,source_sha256:'a'.repeat(64),shape:[5,7,9],affine:[[1,0,0,0],[0,2,0,0],[0,0,3,0],[0,0,0,1]],units:'mm'},
  geometry_identity:{version:'ct-geometry/1.0',sha256:'b'.repeat(64)},review_mode:'original_ct_only',...flags});
const note=(a=item())=>({schema_version:'ct-review-note/0.1',assignment_id:a.id,owner_id:7,case_id:9,protocol_version:a.protocol_version,
  source:a.source,revision:1,notes:'Synthetic private note',exists:true,status:'unverified_draft',...flags});

test('review responses are detached, own-source-bound and not clinically released',()=>{
  const a=item(),before=structuredClone(a),v=validateReviewAssignment(a,7);
  assert.deepEqual(v,before);v.source.shape[0]=99;assert.deepEqual(a,before);
  assert.deepEqual(validateReviewNote(note(a),a,7),note(a));
});
for(const kind of ['owner','other-reader','extra','release','protocol','singular','units','geometry-hash','source-case'])test(`CT assignment rejects ${kind}`,()=>{
  const a=item();if(kind==='owner')a.reviewer_id=8;if(kind==='other-reader')a.other_reviewer_id=8;
  if(kind==='extra')a.prediction={};if(kind==='release')a.clinical_gate_authorized=true;
  if(kind==='protocol')a.protocol_version='';if(kind==='singular')a.source.affine[1]=[0,0,0,0];
  if(kind==='units')a.source.units='unknown';if(kind==='geometry-hash')a.geometry_identity.sha256='invalid';if(kind==='source-case')a.source.case_id=10;
  assert.throws(()=>validateReviewAssignment(a,7));
});
for(const kind of ['owner','source','assignment','release','revision','notes','extra'])test(`private note rejects ${kind}`,()=>{
  const a=item(),n=structuredClone(note(a));if(kind==='owner')n.owner_id=8;if(kind==='source')n.source.source_sha256='c'.repeat(64);
  if(kind==='assignment')n.assignment_id='22222222-2222-4222-8222-222222222222';if(kind==='release')n.training_release_authorized=true;
  if(kind==='revision')n.revision=-1;if(kind==='notes')n.notes='x'.repeat(4001);if(kind==='extra')n.percentage_narrowing=0;
  assert.throws(()=>validateReviewNote(n,a,7));
});
test('source/protocol binding changes are rejected on detail load',async()=>{
  const a=item(),changed={...a,protocol_version:'changed',source_current:true,source_unavailable_reason:null};
  const api=createReviewAssignmentsApi({get:async()=>({status:200,data:changed})});
  await assert.rejects(()=>api.detail(a,7));assert.equal(typeof reviewBinding(a),'string');
});
test('save uses revision CAS and server-enforced false flags without mutating text; 409 is never retried',async()=>{
  const a=item(),calls=[],api=createReviewAssignmentsApi({put:async(...args)=>{calls.push(args);throw Object.assign(new Error('Revision conflict'),{response:{status:409}});}});
  await assert.rejects(()=>api.save(a,7,'unsaved text',1),/conflict/);
  assert.equal(calls.length,1);assert.deepEqual(calls[0][1],{notes:'unsaved text',expected_revision:1,clinical_gate_authorized:false,training_release_authorized:false});
});
test('save validates response revision and notes rather than accepting a success code alone',async()=>{
  const a=item(),api=createReviewAssignmentsApi({put:async()=>({status:200,data:note(a)})});
  await assert.rejects(()=>api.save(a,7,'new text',1));
});
test('original CT download checks exact bytes before creating a Blob',async t=>{
  const a=item(),data=new Uint8Array([1,2,3]).buffer;let blobs=0;
  t.mock.method(globalThis,'Blob',function(){blobs++;});
  const api=createReviewAssignmentsApi({get:async()=>({status:200,data})});
  await assert.rejects(()=>api.download(a));assert.equal(blobs,0);
});
test('matching original CT download is allowed with a generic filename; cancellation is checked after hashing',async()=>{
  const a=item(),data=new Uint8Array([1,2,3]).buffer;
  a.source.source_sha256=Buffer.from(await webcrypto.subtle.digest('SHA-256',data)).toString('hex');
  const api=createReviewAssignmentsApi({get:async()=>({status:200,data})});
  const result=await api.download(a);assert.equal(result.filename,'original-ct-9.nii');assert.equal(result.blob.size,3);
  const controller=new AbortController();controller.abort();await assert.rejects(()=>api.download(a,{signal:controller.signal}));
});
