import test from 'node:test';
import assert from 'node:assert/strict';
import { NIFTI2, readHeader } from 'nifti-reader-js';
import { syntheticNifti } from './e2e/nifti-fixture.js';
import { inspectVolume, sameAffine, validatePair, volumeBudget } from '../src/lib/volume-geometry.js';
import { createSegmentationApi } from '../src/api/segmentation-contract.js';
import { gzipSync } from 'fflate';
import { MAX_TRANSFER_BYTES } from '../src/lib/volume-geometry.js';
import { decode } from '../src/workers/volume.worker.js';
import { loadViewerPair } from '../src/lib/volume-loader.js';
import { releaseViewer } from '../src/lib/niivue-adapter.js';
import { navigateExperimentalCandidate, projectExperimentalCandidates,
  validateExperimentalPreview } from '../src/lib/experimental-candidates.js';
import { loadExperimentalFixture } from './experimental-candidates-fixtures.js';

const id = '12345678-1234-4567-890a-123456789abc';
const array = buffer => buffer.buffer.slice(buffer.byteOffset, buffer.byteOffset + buffer.byteLength);
const ct = () => array(syntheticNifti());
const mask = () => array(syntheticNifti({ mask: true }));
const metadata = geometry => ({ shape: geometry.shape, affine: geometry.affine, xyzt_units: 2 });

test('raw decoding enforces the expected output limit and accepts its boundary', () => {
  const input = new ArrayBuffer(32);
  assert.equal(decode(input, 32), input);
  assert.throws(() => decode(input, 31), /expected output limit/);
});

test('raw and gzip inputs over MAX_TRANSFER_BYTES are rejected before decoding', () => {
  // One zero-initialized buffer tests both paths without populating a large payload.
  const input = new ArrayBuffer(MAX_TRANSFER_BYTES + 1);
  assert.throws(() => decode(input, input.byteLength), /input exceeds.*transfer limit/);
  new Uint8Array(input, 0, 2).set([31, 139]);
  // Invalid gzip would produce a decompression error if the input guard were bypassed.
  assert.throws(() => decode(input, input.byteLength), /input exceeds.*transfer limit/);
});

test('bounded gzip decoding rejects output exceeding the expected uncompressed limit', () => {
  const input = array(gzipSync(new Uint8Array(128 * 1024)));
  assert.throws(() => decode(input, 1024), /Decompressed volume exceeds/);
});

test('gzip input overhead does not count against the uncompressed output limit', () => {
  const original = new Uint8Array([1, 2, 3, 4]);
  const input = array(gzipSync(original));
  assert.ok(input.byteLength > original.byteLength);
  assert.deepEqual(new Uint8Array(decode(input, original.byteLength)), original);
});

test('bounded gzip decoding preserves output across multiple input chunks', () => {
  const original = new Uint8Array(160 * 1024);
  let state = 42;
  for (let index = 0; index < original.length; index++) {
    state ^= state << 13; state ^= state >>> 17; state ^= state << 5;
    original[index] = state & 255;
  }
  const input = array(gzipSync(original));
  assert.ok(input.byteLength > 2 * 64 * 1024);
  assert.deepEqual(new Uint8Array(decode(input, original.byteLength)), original);
});

test('loadViewerPair explicitly requires an AbortSignal before doing any work', async () => {
  await assert.rejects(loadViewerPair(null, 1, null), {
    name: 'TypeError', message: 'loadViewerPair requires an AbortSignal.',
  });
});

test('loadViewerPair rejects an already aborted signal before doing any work', async () => {
  const controller = new AbortController();
  controller.abort();
  await assert.rejects(loadViewerPair(null, 1, null, { signal: controller.signal }), { name: 'AbortError' });
});

for (const throws of [false, true]) test(`viewer release is idempotent when library cleanup ${throws ? 'throws' : 'succeeds'}`, () => {
  const calls = [];
  const viewer = {
    volumes: [{}], back: {}, overlays: [{}],
    onLocationChange: () => { throw new Error('Released callback should be detached.'); },
    onAzimuthElevationChange: () => { throw new Error('Released camera callback should be detached.'); },
    onZoom3DChange: () => { throw new Error('Released zoom callback should be detached.'); },
    cleanup: () => { calls.push('cleanup'); if (throws) throw new Error('Library cleanup failed.'); },
    gl: { getExtension: name => {
      assert.equal(name, 'WEBGL_lose_context');
      calls.push('extension');
      return { loseContext: () => { calls.push('release'); } };
    } },
  };
  assert.doesNotThrow(() => releaseViewer(viewer));
  assert.deepEqual(viewer.volumes, []);
  assert.equal(viewer.back, null);
  assert.deepEqual(viewer.overlays, []);
  assert.doesNotThrow(() => viewer.onLocationChange());
  assert.doesNotThrow(() => viewer.onAzimuthElevationChange());
  assert.doesNotThrow(() => viewer.onZoom3DChange());
  assert.doesNotThrow(() => releaseViewer(viewer));
  assert.deepEqual(calls, ['cleanup', 'extension', 'release']);
});

test('geometry preserves signed affine, spacing and provenance alignment', () => {
  const source = inspectVolume(ct());
  const labels = inspectVolume(mask(), { mask: true });
  assert.equal(source.affine[0][0] < 0, true);
  assert.equal(source.shape.join(), '12,10,8');
  assert.equal(source.units, 'mm');
  assert.equal(validatePair(source, labels, metadata(source)), source);
  assert.throws(() => validatePair(source, { ...labels, shape: [11,10,8] }, metadata(source)), /do not match/);
  const moved = labels.affine.map(row => [...row]); moved[0][3] += 1;
  assert.throws(() => validatePair(source, { ...labels, affine: moved }, metadata(source)), /do not match/);
  assert.throws(() => validatePair(source, labels, { ...metadata(source), shape: [12,10,7] }), /provenance/);
});

test('sform wins over a higher qform code, matching the backend', () => {
  const source = inspectVolume(array(syntheticNifti({ qformCode: 4 })));
  assert.ok(Math.abs(source.affine[0][0] + .7) < .00001);
  assert.equal(source.affine[0][3], 24);
});

test('coded qform-only volumes and NIfTI-2 headers are supported', () => {
  const original = syntheticNifti({ qformCode: 1 }); original.writeInt16LE(0, 254);
  assert.equal(inspectVolume(array(original)).sformCode, 0);
  const one = readHeader(ct());
  const two = Object.assign(new NIFTI2(), one, { magic: 'n+2\0\r\n\x1a\n', vox_offset: 544 });
  const header = new Uint8Array(two.toArrayBuffer());
  const converted = new Uint8Array(header.length + 12*10*8*2);
  converted.set(header); converted.set(new Uint8Array(ct(),352),544);
  assert.equal(inspectVolume(converted.buffer).shape.join(), '12,10,8');
});

for (const [name, change, expected] of [
  ['unknown units', b => { b[123] = 0; }, /unknown/],
  ['metre units', b => { b[123] = 1; }, /not millimetres/],
  ['uncoded orientation', b => { b.writeInt16LE(0,252); b.writeInt16LE(0,254); }, /coded spatial/],
  ['four dimensions', b => b.writeInt16LE(4,40), /three-dimensional/],
  ['shear', b => b.writeFloatLE(.2,284), /Oblique or sheared/],
  ['non-finite affine', b => b.writeFloatLE(NaN,280), /Invalid spatial/],
]) test(`geometry refuses ${name}`, () => {
  const input = syntheticNifti(); change(input);
  assert.throws(() => inspectVolume(array(input)), expected);
});

test('invalid binary payloads, truncation, size and provenance are rejected', () => {
  const labels = syntheticNifti({ mask:true }); labels[352] = 2;
  assert.throws(() => inspectVolume(array(labels), { mask:true }), /binary 0 and 1/);
  assert.throws(() => inspectVolume(ct().slice(0,400)), /incomplete/);
  assert.throws(() => volumeBudget([512,512,512]), /memory budget/);
  assert.throws(() => volumeBudget([512,512,217], 4), /memory budget/);
  assert.equal(volumeBudget([512,512,217], 8).voxels, 56_885_248);
  assert.equal(sameAffine([[1]], [[1]]), false);
});

test('viewer binary requests construct protected routes and propagate progress/cancellation', async () => {
  const controller = new AbortController();
  let config;
  const api = createSegmentationApi({ get: async (url, options) => {
    assert.equal(url, `/cases/1/segmentations/${id}/source`);
    config = options;
    assert.equal(config.responseType, 'arraybuffer');
    options.onDownloadProgress({ loaded: 42 });
    controller.abort();
    assert.equal(config.signal.aborted, true);
    return { status: 200, headers:{'content-type':'application/octet-stream'}, data: ct() };
  } });
  let progress;
  await assert.rejects(api.loadVolume(1, id, 'source', { signal:controller.signal, onProgress:v => { progress = v; } }), { name:'AbortError' });
  assert.deepEqual(progress, {loaded:42,total:null});
  await assert.rejects(api.loadVolume(1,id,'probabilities'), /Invalid viewer/);
});

test('viewer download decodes protected error bodies and refuses HTML or empty data', async () => {
  for (const data of [new ArrayBuffer(0), ct()]) {
    const api = createSegmentationApi({ get:async () => ({status:200,headers:{'content-type':'text/html'},data}) });
    await assert.rejects(api.loadVolume(1,id,'source'), /supported medical volume/);
  }
  const api = createSegmentationApi({get:async () => { throw { response:{ status:409, data:new TextEncoder().encode('{"detail":"Input changed"}').buffer } }; }});
  await assert.rejects(api.loadVolume(1,id,'mask'), error => error.message === 'Input changed');
});
const experimentalFixture = () => loadExperimentalFixture();

test('experimental preview verifies actual mask identity and preserves detached source-bound coordinates',async()=>{
  const f=await experimentalFixture(),before=structuredClone(f.preview);
  const verified=await validateExperimentalPreview(f.preview,f.geometry,f.segmentation,f.verifiedMask);
  assert.deepEqual(verified,before);assert.notEqual(verified,f.preview);assert.deepEqual(f.preview,before);
  assert.equal(verified.notice,'EXPERIMENTAL — NOT A DIAGNOSIS');
  assert.equal(verified.measurement_status,'measurement_unavailable_no_validated_gate');
});

for(const defect of ['mask','source','parent','geometry','coordinates','outside-mask','reference','gate','severity','counts','duplicate','missing-branch'])test(`experimental preview rejects ${defect} without mutating input`,async()=>{
  const f=await experimentalFixture(),p=f.preview,c=p.candidates[0];
  if(defect==='mask')p.source.mask_sha256='d'.repeat(64);
  if(defect==='source')p.source.source_sha256='d'.repeat(64);
  if(defect==='parent')p.source.parent_segmentation_result_id='20000001-1234-4567-890a-123456789abc';
  if(defect==='geometry')p.geometry.affine[0][3]++;
  if(defect==='coordinates')c.world_ras_mm[0]++;
  if(defect==='outside-mask'){c.sample_ijk=[0,0,0];c.world_ras_mm=p.geometry.affine.slice(0,3).map(r=>r[3]);}
  if(defect==='reference')p.source.mask_role='reference_annotation';
  if(defect==='gate')p.validation_gate={validated:true};
  if(defect==='severity')c.severity='severe';
  if(defect==='counts')p.branches[0].abstained_sections=20;
  if(defect==='duplicate')p.candidates.push(structuredClone(c));
  if(defect==='missing-branch')c.branch_id='unrelated';
  const before=structuredClone(p);
  await assert.rejects(validateExperimentalPreview(p,f.geometry,f.segmentation,f.verifiedMask));
  assert.deepEqual(p,before);
});

test('experimental no-candidate and abstained states are distinct, not quantitative normal findings',async()=>{
  for(const state of ['no_candidates_in_evaluable_sections','abstained']){
    const f=await loadExperimentalFixture('flipped',state==='abstained'?'abstained_preview':'no_candidate_preview');
    assert.equal((await validateExperimentalPreview(f.preview,f.geometry,f.segmentation,f.verifiedMask)).status,state);
  }
});

test('experimental oblique preview does not bypass the current viewer limitation',async()=>{
  const f=await experimentalFixture(),g=structuredClone(f.geometry);g.affine=[[.8,-.6,0,0],[.6,.8,0,0],[0,0,1,0],[0,0,0,1]];f.preview.geometry=g;
  await assert.rejects(validateExperimentalPreview(f.preview,g,f.segmentation,f.verifiedMask),/Oblique/);
});

test('experimental markers reuse RAS projection without entering clinical result contracts',async()=>{
  const f=await experimentalFixture(),calls=[],viewer={volumes:[{dimsRAS:[3,...f.geometry.shape]}],canvas:{width:100,height:100},scene:{crosshairPos:[.5,.5,.5]},sliceTypeAxial:0,sliceTypeCoronal:1,sliceTypeSagittal:2,
    mm2frac:world=>{calls.push(world);return [.5,.5,.5];},frac2canvasPosWithTile:()=>({pos:[50,50]}),canvasPos2frac:()=>[.5,.5,.5],drawScene(){},onLocationChange(){}};
  const markers=projectExperimentalCandidates(viewer,f.preview,'candidate-001');
  assert.equal(markers.length,3);assert.ok(markers.every(p=>p.id==='candidate-001'&&p.selected));
  navigateExperimentalCandidate(viewer,f.preview.candidates[0]);
  assert.deepEqual(calls[0],f.preview.candidates[0].world_ras_mm);assert.deepEqual(viewer.scene.crosshairPos,[.5,.5,.5]);
});

for (const layout of ['flipped','permuted']) test(`public preview validator accepts actual serialized backend output (${layout})`,async()=>{
  const f=await loadExperimentalFixture(layout),before=structuredClone(f.preview);
  const actualSerializedOutput=JSON.parse(JSON.stringify(f.preview));
  assert.ok(actualSerializedOutput.branches[0].sections.length>2);
  assert.equal(f.preview.source.mask_sha256,f.verifiedMask.sha256);
  const accepted=await validateExperimentalPreview(actualSerializedOutput,f.geometry,f.segmentation,f.verifiedMask);
  assert.deepEqual(accepted,before);assert.deepEqual(f.preview,before);
});

for (const defect of ['removed-support','nonexistent-support','false-count','interval-outside','interval-other-rows','support-gap',
  'unsupported-center','null-pixels','zero-pixels','null-area','negative-area','wrong-area','ambiguous-component','inadequate-references',
  'nonfinite-arc','unordered-arc','row-coordinates','global-status','global-reason','branch-status','missing-candidate',
  'fractional-reference-minimum','low-reference-minimum','fractional-candidate-minimum','low-candidate-minimum']) {
  test(`public preview validator rejects inconsistent backend evidence: ${defect}`,async()=>{
    const f=await experimentalFixture(),p=f.preview,branch=p.branches[0],candidate=p.candidates[0];
    const row=branch.sections.find(r=>r.status==='evaluable_candidate_only');
    if(defect==='removed-support'){branch.sections=[];branch.evaluable_sections=0;branch.abstained_sections=0;}
    if(defect==='nonexistent-support')candidate.supporting_sections=branch.sections.length+1;
    if(defect==='false-count')candidate.supporting_sections++;
    if(defect==='interval-outside')candidate.interval_s_mm=[1000,1002];
    if(defect==='interval-other-rows')candidate.interval_s_mm=[row.s_mm,row.s_mm+candidate.supporting_sections-1];
    if(defect==='support-gap')branch.sections.splice(branch.sections.findIndex(r=>r.s_mm===candidate.interval_s_mm[0])+1,1);
    if(defect==='unsupported-center'){candidate.sample_ijk=[...row.sample_ijk];candidate.world_ras_mm=[...row.world_ras_mm];}
    if(defect==='null-pixels')row.pixel_count=null;
    if(defect==='zero-pixels')row.pixel_count=0;
    if(defect==='null-area')row.diagnostic_area_mm2=null;
    if(defect==='negative-area')row.diagnostic_area_mm2=-1;
    if(defect==='wrong-area')row.diagnostic_area_mm2+=1;
    if(defect==='ambiguous-component')row.plane_components=2;
    if(defect==='inadequate-references')row.reference_samples_each_side=[0,0];
    if(defect==='nonfinite-arc')row.s_mm=NaN;
    if(defect==='unordered-arc')row.s_mm=branch.sections[0].s_mm;
    if(defect==='row-coordinates')row.world_ras_mm[0]+=1;
    if(defect==='global-status'){p.status='abstained';p.reason='no_evaluable_reference_support';}
    if(defect==='global-reason')p.reason='no_evaluable_reference_support';
    if(defect==='branch-status'){row.status='abstained';row.reason='insufficient_bidirectional_reference';branch.evaluable_sections--;branch.abstained_sections++;}
    if(defect==='missing-candidate'){p.candidates=[];p.status='no_candidates_in_evaluable_sections';}
    if(defect==='fractional-reference-minimum')p.parameters.minimum_reference_samples_each_side=2.5;
    if(defect==='low-reference-minimum')p.parameters.minimum_reference_samples_each_side=1;
    if(defect==='fractional-candidate-minimum')p.parameters.minimum_candidate_sections=2.5;
    if(defect==='low-candidate-minimum')p.parameters.minimum_candidate_sections=1;
    const before=structuredClone(p);
    await assert.rejects(validateExperimentalPreview(p,f.geometry,f.segmentation,f.verifiedMask));
    assert.deepEqual(p,before);
  });
}
