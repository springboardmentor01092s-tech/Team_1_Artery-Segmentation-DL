import test from 'node:test';
import assert from 'node:assert/strict';
import { createStenosisResultsApi, validateResultResponse } from '../src/api/stenosis-results-contract.js';
import { geometryFingerprint, matchingLesion, validateLocalizationBinding } from '../src/lib/stenosis-results.js';
import { navigateToLesion, projectLesionMarkers } from '../src/lib/lesion-viewer.js';
import { geometryFixture, lesionIds, regionId, resultFixture } from './stenosis-results-fixtures.js';
import { GATE_UNAVAILABLE_REASON, measurementPresentation, requireMeasurementGate } from '../src/lib/quantitative-gate.js';

test('completed multiple and genuinely empty results validate', async () => {
  for (const count of [0, 3]) {
    const root = await resultFixture({count});
    assert.equal(await validateResultResponse(root, 1, root.result.analysis_id), root);
  }
});

test('Python-compatible geometry fingerprint changes with source, axis, spacing and origin', async () => {
  const root = await resultFixture();
  assert.equal(await geometryFingerprint(geometryFixture, 'a'.repeat(64)), 'fc76353587232e122d6e1541c90290ecc742029049792babc56c43d8e25ae1a5');
  for (const field of ['hash','shape','affine']) {
    const geometry = structuredClone(geometryFixture);
    if (field === 'shape') geometry.shape[0]++;
    if (field === 'affine') geometry.affine[0][3]++;
    assert.notEqual(await geometryFingerprint(geometry, (field === 'hash' ? 'b' : 'a').repeat(64)), root.geometry_fingerprint);
  }
});

for (const kind of ['case','parent','hash','fingerprint','bounds','world','nan','singular','duplicate','incomplete','missing_reason','invalid_region','percent','geometry_units']) test(`rejects malformed ${kind} before presentation`, async () => {
  const root = await resultFixture();
  if (kind === 'case') root.case_id = 2;
  if (kind === 'parent') root.segmentation.id = regionId;
  if (kind === 'hash') root.segmentation.metadata.source_sha256 = 'b'.repeat(64);
  if (kind === 'fingerprint') root.geometry_fingerprint = 'b'.repeat(64);
  if (kind === 'bounds') root.result.lesions[0].location.voxel_indices[0] = 12;
  if (kind === 'world') root.result.lesions[0].location.world_coordinates[0]++;
  if (kind === 'nan') root.result.lesions[0].location.world_coordinates[0] = NaN;
  if (kind === 'singular') root.result.provenance.geometry.affine[0][0] = 0;
  if (kind === 'duplicate') root.result.lesions[1].lesion_id = lesionIds[0];
  if (kind === 'incomplete') root.result.state = 'running';
  if (kind === 'missing_reason') root.result.lesions[0].measurements.reference_diameter.unavailable_reason = null;
  if (kind === 'percent') root.result.lesions[0].measurements.percentage_narrowing = {value:101,unit:'percent',unavailable_reason:null,method_id:'test',method_version:'1',definition:'test-only'};
  if (kind === 'invalid_region') root.result.lesions[0].candidate_region = {artifact_id:regionId,geometry:root.result.provenance.geometry};
  if (kind === 'geometry_units') root.result.provenance.geometry.world_unit = 'unknown';
  await assert.rejects(validateResultResponse(root,1,root.result.analysis_id));
});

test('zero is withheld without a validated gate; unavailable location remains explicit', async () => {
  const root = await resultFixture();
  root.result.lesions[0].measurements.minimum_lumen_diameter = {value:0,unit:'mm',unavailable_reason:null,method_id:'test-fixture',method_version:'1'};
  root.result.lesions[1].location = null;
  root.result.lesions[1].localization_unavailable_reason = {code:'not_provided',message:'Test-only unavailable localization'};
  await assert.rejects(validateResultResponse(root,1,root.result.analysis_id), /validated quantitative/);
  root.result.lesions[0].measurements.minimum_lumen_diameter = {value:null,unit:'mm',unavailable_reason:{code:'not_integrated',message:GATE_UNAVAILABLE_REASON}};
  await validateResultResponse(root,1,root.result.analysis_id);
  assert.equal(root.result.lesions[1].location, null);
});

for (const field of ['reference_diameter','minimum_lumen_diameter','percentage_narrowing']) {
  for (const value of [0, 25]) test(`rejects unregistered gate for ${field}=${value} before presentation`, async () => {
    const root = await resultFixture();
    const measurement = {value,unit:field==='percentage_narrowing'?'percent':'mm',unavailable_reason:null,
      method_id:'synthetic-test-only',method_version:'v1',definition:'Negative bypass fixture only',
      validation_gate:{gate_id:'synthetic-unregistered',gate_version:'v1',evidence_sha256:'a'.repeat(64),
        analysis_method_id:root.result.provenance.method_id,analysis_method_version:root.result.provenance.method_version,
        source_sha256:root.result.provenance.source.source_sha256,checkpoint_sha256:null,validated:true}};
    root.result.lesions[0].measurements[field] = measurement;
    await assert.rejects(validateResultResponse(root,1,root.result.analysis_id), /validated quantitative/);
    assert.throws(()=>requireMeasurementGate(measurement,root.result.provenance), /validated quantitative/);
    const displayed = measurementPresentation(measurement,root.result.provenance);
    assert.equal(displayed.reportable,false);
    assert.equal(displayed.text,`Unavailable: ${GATE_UNAVAILABLE_REASON}`);
    assert.ok(!displayed.text.includes(`${value} ${measurement.unit}`));
  });
}

test('direct presentation without adapter preserves unavailable reason and never self-validates supplied claims', () => {
  assert.equal(measurementPresentation({value:null,unavailable_reason:{message:'Synthetic original reason'}}).text,'Unavailable: Synthetic original reason');
  for (const value of [undefined, {value:0,unit:'mm',validated:true}, {value:35,unit:'percent',validation_gate:{gate_id:'__proto__'}}]) {
    assert.equal(measurementPresentation(value).reportable,false);
  }
});

test('results reuse authenticated relative API and forward cancellation', async () => {
  const root = await resultFixture(); const controller = new AbortController(); const calls = [];
  const api = createStenosisResultsApi({get:async (...args) => {calls.push(args);return {status:200,data:root};}});
  await api.result(1,root.result.analysis_id,{signal:controller.signal});
  assert.deepEqual(calls, [[`/cases/1/stenosis/analyses/${root.result.analysis_id}/result`,{signal:controller.signal}]]);
});

test('region API rejects text and decodes structured binary errors', async () => {
  const root = await resultFixture();
  const api = createStenosisResultsApi({get:async () => ({status:200,data:new TextEncoder().encode('<html>').buffer,headers:{'content-type':'text/html'}})});
  await assert.rejects(api.region(1,root.result.analysis_id,lesionIds[0],regionId), /volume/);
  const failure = Object.assign(new Error('HTTP 409'), {response:{data:new TextEncoder().encode(JSON.stringify({detail:{contract_version:'1.0',code:'source_changed',message:'Source is stale'}})).buffer}});
  await assert.rejects(createStenosisResultsApi({get:async()=>{throw failure;}}).region(1,root.result.analysis_id,lesionIds[0],regionId), {message:'Source is stale',code:'source_changed'});
});

test('ambiguous exact positions never select an arbitrary candidate', async () => {
  const root = await resultFixture(); const [a,b] = root.result.lesions;
  b.location = structuredClone(a.location);
  assert.deepEqual(matchingLesion([a,b],a.location.world_coordinates,null),{id:null,ambiguous:true});
  assert.deepEqual(matchingLesion([a,b],a.location.world_coordinates,b.lesion_id),{id:b.lesion_id,ambiguous:true});
  assert.deepEqual(matchingLesion([a],a.location.world_coordinates,null),{id:a.lesion_id,ambiguous:false});
  assert.deepEqual(matchingLesion([a],[99,99,99],null),{id:null,ambiguous:false});
});

test('localization binding rejects different case, parent or displayed affine', async () => {
  const root = await resultFixture();
  validateLocalizationBinding(root,geometryFixture,1,root.segmentation.id);
  for (const [geometry,caseId,parent] of [[geometryFixture,2,root.segmentation.id],[geometryFixture,1,regionId],[{...geometryFixture,affine:[[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]]},1,root.segmentation.id]]) {
    assert.throws(()=>validateLocalizationBinding(root,geometry,caseId,parent));
  }
});

test('navigation uses validated RAS mm through NiiVue, never array indices as world positions', async () => {
  const root = await resultFixture(); const calls = []; const fraction=[.25,.35,.45];
  const viewer = {scene:{},mm2frac:(...args)=>{calls.push(args);return fraction;},drawScene:()=>calls.push('draw'),onLocationChange:()=>calls.push('location')};
  navigateToLesion(viewer,root.result.lesions[0],geometryFixture);
  assert.deepEqual(calls,[ [root.result.lesions[0].location.world_coordinates,0,true], 'draw', 'location' ]);
  assert.equal(viewer.scene.crosshairPos,fraction);
});

test('marker projection omits off-slice and edge-clamped points', async () => {
  const root = await resultFixture(); const viewer = {canvas:{width:100,height:100},scene:{crosshairPos:[.5,.5,.5]},volumes:[{dimsRAS:[3,12,10,8]}],sliceTypeAxial:0,sliceTypeCoronal:1,sliceTypeSagittal:2,
    mm2frac:()=>[.5,.5,.5],frac2canvasPosWithTile:()=>({pos:[30,40],tileIndex:0}),canvasPos2frac:()=>[.5,.5,.5]};
  assert.equal(projectLesionMarkers(viewer,[root.result.lesions[0]],lesionIds[0]).length,3);
  viewer.canvasPos2frac = ()=>[.1,.1,.1];
  assert.equal(projectLesionMarkers(viewer,[root.result.lesions[0]],lesionIds[0]).length,0);
  viewer.scene.crosshairPos=[0,0,0];
  assert.equal(projectLesionMarkers(viewer,[root.result.lesions[0]],lesionIds[0]).length,0);
});
