import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {gzipSync} from 'fflate';
import {syntheticNifti} from './e2e/nifti-fixture.js';
import {verifyOriginalCt,ctReviewNativePoint} from '../src/lib/ct-review-volume.js';
import {loadAssignedCt,prepareOriginalCt} from '../src/lib/ct-review-loader.js';
import {inspectVolume} from '../src/lib/volume-geometry.js';
import {createReviewAssignmentsApi} from '../src/api/review-assignments-contract.js';
const array=b=>b.buffer.slice(b.byteOffset,b.byteOffset+b.byteLength);
function fixture(compressed=true){
  const raw=array(syntheticNifti()),ct=compressed?array(gzipSync(new Uint8Array(raw))):raw,g=inspectVolume(raw);
  const source={case_id:1,source_sha256:createHash('sha256').update(new Uint8Array(ct)).digest('hex'),shape:g.shape,affine:g.affine,units:'mm'};
  const assignment={id:'11111111-1111-4111-8111-111111111111',reviewer_id:7,slot:'R1',case_id:1,protocol_version:'synthetic-unapproved',
    source,geometry_identity:{version:'ct-geometry/1.0',sha256:'b'.repeat(64)},review_mode:'original_ct_only',
    clinical_gate_authorized:false,training_release_authorized:false,reader_independence_verified:false,qualification_verified:false,
    source_current:true,source_unavailable_reason:null};
  return {raw,ct,source,assignment};
}
for(const compressed of [false,true])test(`original CT verifies exact ${compressed?'gzip':'raw'} bytes without a mask`,async()=>{
  const f=fixture(compressed),p=await verifyOriginalCt(f.ct,f.source);
  assert.deepEqual(new Uint8Array(p.ct),new Uint8Array(f.raw));assert.deepEqual(Object.keys(p).sort(),['ct','geometry']);
  assert.deepEqual(p.geometry.shape,[12,10,8]);
});
for(const kind of ['hash','shape','affine','units','missing-hash','bad-nifti'])test(`original CT fails closed for ${kind}`,async()=>{
  const f=fixture();
  if(kind==='hash')f.source.source_sha256='0'.repeat(64);
  if(kind==='missing-hash')delete f.source.source_sha256;
  if(kind==='shape')f.source.shape=[10,12,8];
  if(kind==='affine')f.source.affine[0][3]+=1;
  if(kind==='units')f.source.units='unknown';
  if(kind==='bad-nifti'){f.ct=new Uint8Array([1,2,3]).buffer;f.source.source_sha256=createHash('sha256').update(new Uint8Array(f.ct)).digest('hex');}
  await assert.rejects(()=>verifyOriginalCt(f.ct,f.source));
});
test('native display coordinates agree with independent flipped/permuted geometry',()=>{
  const geometry={shape:[12,10,8],affine:[[0,-1.2,0,24],[-.7,0,0,-13],[0,0,2.5,42],[0,0,0,1]]};
  // Physical coordinates calculated directly: R=24-1.2*j, A=-13-.7*i, S=42+2.5*k.
  assert.deepEqual(ctReviewNativePoint([19.2,-14.4,49.5],geometry),[2,4,3]);
  assert.equal(ctReviewNativePoint([100,-14.4,49.5],geometry),null);
});
function environment(t,hold=false){
  const descriptors=new Map(),workers=[];let token='synthetic-session';
  for(const [name,value] of Object.entries({isSecureContext:true,localStorage:{getItem:()=>token},Worker:class{
    constructor(){workers.push(this);}
    terminate(){this.terminated=true;}
    postMessage(message){this.message=message;const send=async()=>{
      try{const data=await verifyOriginalCt(message.ct,message.source);this.onmessage({data});}catch(e){this.onmessage({data:{error:e.message}});}
    };this.release=send;if(!hold)queueMicrotask(send);}
  }})){
    descriptors.set(name,Object.getOwnPropertyDescriptor(globalThis,name));Object.defineProperty(globalThis,name,{configurable:true,value});
  }
  t.after(()=>{for(const [name,desc] of descriptors){if(desc)Object.defineProperty(globalThis,name,desc);else delete globalThis[name];}});
  return {workers,changeSession:()=>{token='different-synthetic-session';}};
}
test('assignment CT loader checks pre/post freshness and never requests prediction APIs',async t=>{
  const env=environment(t),f=fixture(),calls=[],controller=new AbortController();
  const api={detail:async()=>{calls.push('detail');return structuredClone(f.assignment);},loadOriginalCt:async()=>{calls.push('original');return f.ct;}};
  const packet=await loadAssignedCt(api,f.assignment,7,{signal:controller.signal});
  assert.deepEqual(calls,['detail','original','detail']);assert.equal(env.workers.length,1);assert.equal(env.workers[0].terminated,true);
  assert.deepEqual(Object.keys(env.workers[0].message).sort(),['ct','source']);assert.ok(packet.ct);
});
for(const kind of ['source-before','source-after','session','owner','binding'])test(`loader rejects ${kind} without applying CT`,async t=>{
  const env=environment(t),f=fixture();let details=0,downloaded=0;
  const api={detail:async()=>{const a=structuredClone(f.assignment);details++;
    if(kind==='binding')a.protocol_version='changed';
    if(kind==='source-before'||kind==='source-after'&&details===2){a.source_current=false;a.source_unavailable_reason='changed';}return a;},
    loadOriginalCt:async()=>{downloaded++;if(kind==='session')env.changeSession();return f.ct;}};
  await assert.rejects(()=>loadAssignedCt(api,f.assignment,kind==='owner'?8:7,{signal:new AbortController().signal}));
  if(kind==='source-before'||kind==='binding'||kind==='owner')assert.equal(downloaded,0);
});
test('cancelled worker cannot complete an old CT load and always terminates',async t=>{
  const env=environment(t,true),f=fixture(),controller=new AbortController();
  const pending=prepareOriginalCt(f.ct,f.source,{signal:controller.signal});controller.abort();
  await assert.rejects(pending,{name:'AbortError'});assert.equal(env.workers[0].terminated,true);
  await env.workers[0].release();
});
test('loader refuses missing AbortSignal and exceeded existing voxel budget before download',async t=>{
  environment(t);const f=fixture(),calls=[];const api={detail:async()=>{calls.push(1);}};
  await assert.rejects(()=>loadAssignedCt(api,f.assignment,7),/AbortSignal/);
  f.assignment.source.shape=[512,512,257];await assert.rejects(()=>loadAssignedCt(api,f.assignment,7,{signal:new AbortController().signal}),/memory budget/);
  assert.deepEqual(calls,[]);
});
test('source download uses only assignment source route and aborts oversized progress',async()=>{
  const f=fixture(),calls=[];
  const api=createReviewAssignmentsApi({get:async(url,opts)=>{calls.push(url);opts.onDownloadProgress({loaded:1,total:513*1024*1024});
    return {status:200,data:f.ct};}});
  await assert.rejects(()=>api.loadOriginalCt(f.assignment),/transfer limit/);
  assert.deepEqual(calls,[`/review-assignments/${f.assignment.id}/source`]);
});
