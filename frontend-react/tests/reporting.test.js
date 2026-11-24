import test from 'node:test';
import assert from 'node:assert/strict';
import {createStenosisReportingApi,validateSummary,validateReport,validateIndex} from '../src/api/stenosis-reporting-contract.js';
import {downloadRecords,reportJsonBlob,downloadCaseWorkflow} from '../src/lib/exports.js';
import {workflowFixture} from './case-workflow-fixtures.js';
import {summaryFixture,indexFixture,reportFixture} from './reporting-fixtures.js';
import {loadExperimentalFixture} from './experimental-candidates-fixtures.js';
import {validateExperimentalPreview} from '../src/lib/experimental-candidates.js';
import { annotationSource, newAnnotationDraft, newDraftLesion, annotationDraftBlob,
  validateAnnotationDraft, worldToNativeIjk } from '../src/lib/annotation-draft.js';
import {createAnnotationDraftApi,annotationBinding,validateAnnotationResponse} from '../src/api/annotation-drafts-contract.js';

const draftSource = () => annotationSource(1,{case_id:1,id:'11111111-1111-4111-8111-111111111111',metadata:{source_sha256:'a'.repeat(64)}},
  {shape:[20,30,40],affine:[[-2,0,0,10],[0,3,0,20],[0,0,4,-30],[0,0,0,1]],units:'mm'});
const draftWithWorksheet = () => { const source=draftSource(),draft=newAnnotationDraft(source);draft.proposed_lesions.push(newDraftLesion());return {source,draft}; };

function privateResponse(document=newAnnotationDraft(draftSource()),revision=1) {
  return {id:'33333333-3333-4333-8333-333333333333',patient_id:1,case_id:1,owner_id:1,revision,
    status:'unverified_server_draft',source_current:true,source_unavailable_reason:null,
    geometry_identity:{version:'ct-geometry/1.0',sha256:'c'.repeat(64)},
    segmentation_provenance:{segmentation_result_id:document.source.segmentation_result_id,checkpoint_sha256:'a'.repeat(64),
      mask_sha256:'b'.repeat(64),probabilities_sha256:'d'.repeat(64),threshold:.5},document,
    clinical_gate_authorized:false,training_release_authorized:false,
    created_at:'2026-11-23T00:00:00Z',updated_at:'2026-11-23T00:00:00Z'};
}
const privateContext=()=>({source:draftSource(),ownerId:1,checkpointSha256:'a'.repeat(64)});

test('private draft API snapshots the local document, uses known routes and sends exact revision',async()=>{
  const doc=newAnnotationDraft(draftSource()),before=structuredClone(doc),calls=[];
  const api=createAnnotationDraftApi({post:async(...args)=>{calls.push(args);return {status:201,data:privateResponse(args[1].document)};},
    put:async(...args)=>{calls.push(args);return {status:200,data:privateResponse(args[1].document,2)};}});
  const saved=await api.save(privateContext(),doc);
  const current={id:saved.id,revision:1,binding:annotationBinding(saved)};
  const updated=await api.save(privateContext(),doc,current);
  assert.equal(updated.revision,2);assert.deepEqual(doc,before);
  assert.equal(calls[0][0],'/cases/1/annotation-drafts');
  assert.equal(calls[1][0],`/cases/1/annotation-drafts/${saved.id}`);
  assert.equal(calls[1][1].expected_revision,1);assert.deepEqual(calls[1][1].document,before);
});
for(const kind of ['owner','case','hash','geometry','checkpoint','revision','release','training','document','binding']) {
  test(`private draft response rejects mismatched ${kind} before application`,()=>{
    const value=privateResponse(),expected={revision:1,binding:annotationBinding(value)};
    if(kind==='owner')value.owner_id=2;if(kind==='case')value.case_id=2;
    if(kind==='hash')value.document.source.source_sha256='b'.repeat(64);
    if(kind==='geometry')value.geometry_identity.version='unknown';
    if(kind==='checkpoint')value.segmentation_provenance.checkpoint_sha256='e'.repeat(64);
    if(kind==='revision')value.revision=2;if(kind==='release')value.clinical_gate_authorized=true;
    if(kind==='training')value.training_release_authorized=true;
    if(kind==='document')value.document.training_release_authorized=true;
    if(kind==='binding')value.geometry_identity.sha256='f'.repeat(64);
    assert.throws(()=>validateAnnotationResponse(value,privateContext(),expected));
  });
}
test('private draft save preserves HTTP 409 and never retries or changes the supplied revision',async()=>{
  const error=Object.assign(new Error('Revision conflict'),{response:{status:409}}),calls=[];
  const api=createAnnotationDraftApi({put:async(...args)=>{calls.push(args);throw error;}});
  const current={id:privateResponse().id,revision:1,binding:annotationBinding(privateResponse())},before=structuredClone(current);
  await assert.rejects(()=>api.save(privateContext(),newAnnotationDraft(draftSource()),current),value=>value===error);
  assert.equal(calls.length,1);assert.deepEqual(current,before);assert.equal(calls[0][1].expected_revision,1);
});
test('private draft API refuses malformed documents before any network request',async()=>{
  let calls=0;const api=createAnnotationDraftApi({post:async()=>{calls++;}}),doc=newAnnotationDraft(draftSource());
  doc.source.affine[0]=[0,0,0,0];
  await assert.rejects(()=>api.save(privateContext(),doc));assert.equal(calls,0);
});
test('private draft discovery sends current run and validates private pagination',async()=>{
  const result=privateResponse(),row={id:result.id,case_id:1,owner_id:1,revision:1,
    segmentation_result_id:result.document.source.segmentation_result_id,source_sha256:result.document.source.source_sha256,
    status:result.status,updated_at:result.updated_at,clinical_gate_authorized:false,training_release_authorized:false};
  const calls=[],page={items:[row],limit:20,offset:0,next_offset:null,offset_limit_reached:false};
  const api=createAnnotationDraftApi({get:async(...args)=>{calls.push(args);return {status:200,data:page};}});
  assert.deepEqual(await api.list(privateContext()),page);
  assert.equal(calls[0][1].params.segmentation_result_id,row.segmentation_result_id);
  page.items[0].owner_id=2;await assert.rejects(()=>api.list(privateContext()));
  await assert.rejects(()=>api.list(privateContext(),1_000_001));
});

test('annotation draft starts without findings or invented measurements',async()=>{
  const source=draftSource(),blank=newAnnotationDraft(source);
  assert.deepEqual(blank.proposed_lesions,[]);assert.equal(blank.training_eligible,false);
  const {draft}=draftWithWorksheet(),body=JSON.parse(await annotationDraftBlob(draft,source).text());
  assert.equal(body.proposed_lesions[0].minimum_lumen_diameter_mm,null);
  assert.equal(body.proposed_lesions[0].percentage_narrowing,null);assert.equal(body.proposed_lesions[0].severity_category,null);
});
test('draft crosshair capture uses native coordinates with independent flipped-axis expected values',()=>{
  assert.deepEqual(worldToNativeIjk([0,38,-2],draftSource()),[5,6,7]);
});
test('draft crosshair capture respects permuted anisotropic axes',()=>{
  const source=draftSource();source.affine=[[0,0,-4,10],[-2,0,0,20],[0,3,0,-30],[0,0,0,1]];
  assert.deepEqual(worldToNativeIjk([-18,10,-12],source),[5,6,7]);
});
test('draft point capture refuses out-of-grid and nonfinite locations',()=>{
  assert.throws(()=>worldToNativeIjk([1000,0,0],draftSource()),/outside/);
  assert.throws(()=>worldToNativeIjk([NaN,0,0],draftSource()),/Invalid/);
});
test('draft point capture refuses singular transforms',()=>{
  const source=draftSource();source.affine[0]=[0,0,0,10];assert.throws(()=>worldToNativeIjk([10,20,-30],source));
});
test('draft source refuses cross-case parent records and missing units',()=>{
  assert.throws(()=>annotationSource(2,{case_id:1,id:'11111111-1111-4111-8111-111111111111',metadata:{source_sha256:'a'.repeat(64)}},{...draftSource(),units:'mm'}));
  assert.throws(()=>newAnnotationDraft({...draftSource(),units:'unknown'}));assert.throws(()=>newAnnotationDraft({}));
});
for (const flag of ['clinical_validation','training_eligible','quantitative_gate_authorized','reader_independence_verified',
  'clinical_gate_authorized','training_release_authorized']) test(`draft refuses forged ${flag}`,()=>{
  const {source,draft}=draftWithWorksheet();draft[flag]=true;assert.throws(()=>annotationDraftBlob(draft,source));
});

const invalidDraftSources = {
  singular: source=>{source.affine[0]=[0,0,0,0];},
  near_singular: source=>{source.affine=[[1,1,0,0],[0,1e-10,0,0],[0,0,1,0],[0,0,0,1]];},
  nonfinite: source=>{source.affine[0][0]=Infinity;},
  nonhomogeneous: source=>{source.affine[3][0]=1;},
  missing_row: source=>{source.affine.pop();},
  sparse_row: source=>{delete source.affine[1][0];},
  sparse_shape: source=>{delete source.shape[0];},
  zero_dimension: source=>{source.shape[0]=0;},
  fractional_dimension: source=>{source.shape[0]=1.5;},
  unsafe_voxel_count: source=>{source.shape=[Number.MAX_SAFE_INTEGER,2,2];},
  unknown_units: source=>{source.units='unknown';},
  nonstring_hash: source=>{source.source_sha256=[source.source_sha256];},
};
for (const [kind,change] of Object.entries(invalidDraftSources)) for (const operation of ['capture','restore','export']) {
  test(`shared annotation geometry validation rejects ${kind} during ${operation}`,()=>{
    const {source,draft}=draftWithWorksheet();change(source);draft.source=structuredClone(source);
    if(operation==='capture')assert.throws(()=>worldToNativeIjk([0,38,-2],source),/Invalid/);
    if(operation==='restore')assert.throws(()=>validateAnnotationDraft(draft,source),/Invalid/);
    if(operation==='export')assert.throws(()=>annotationDraftBlob(draft,source),/Invalid/);
  });
}
for (const kind of ['shape','affine','units','hash','run','case']) for (const operation of ['capture','restore','export']) {
  test(`annotation ${operation} rejects a source with mismatched ${kind}`,()=>{
    const {source,draft}=draftWithWorksheet(),other=structuredClone(source);
    if(kind==='shape')other.shape[0]++;
    if(kind==='affine')other.affine[0][3]++;
    if(kind==='units')other.units='m';
    if(kind==='hash')other.source_sha256='b'.repeat(64);
    if(kind==='run')other.segmentation_result_id='22222222-2222-4222-8222-222222222222';
    if(kind==='case')other.case_id=2;
    draft.source=other;
    if(operation==='capture')assert.throws(()=>worldToNativeIjk([0,38,-2],other,source),/Invalid/);
    if(operation==='restore')assert.throws(()=>validateAnnotationDraft(draft,source),/Invalid/);
    if(operation==='export')assert.throws(()=>annotationDraftBlob(draft,source),/Invalid/);
  });
}
test('new and round-tripped local drafts never authorize clinical or training release',async()=>{
  const {source,draft}=draftWithWorksheet(),before=structuredClone(draft);
  for(const value of [draft,JSON.parse(await annotationDraftBlob(draft,source).text())]) {
    assert.equal(value.clinical_gate_authorized,false);assert.equal(value.training_release_authorized,false);
    validateAnnotationDraft(value,source);
  }
  assert.deepEqual(draft,before);
  delete draft.training_release_authorized;
  assert.throws(()=>validateAnnotationDraft(draft,source));
});
test('invalid geometry never allocates an export Blob',()=>{
  const {source,draft}=draftWithWorksheet(),NativeBlob=globalThis.Blob;
  let allocated=0;
  globalThis.Blob=class extends NativeBlob { constructor(...args){allocated++;super(...args);} };
  try {
    draft.source.affine[0]=[0,0,0,0];
    assert.throws(()=>annotationDraftBlob(draft,source),/Invalid/);
    assert.equal(allocated,0);
  } finally { globalThis.Blob=NativeBlob; }
});
for (const kind of ['case','hash','parent','shape','affine']) test(`draft restore rejects mismatched ${kind}`,()=>{
  const {source,draft}=draftWithWorksheet();
  if(kind==='case')draft.source.case_id=2;if(kind==='hash')draft.source.source_sha256='b'.repeat(64);
  if(kind==='parent')draft.source.segmentation_result_id='22222222-2222-4222-8222-222222222222';
  if(kind==='shape')draft.source.shape[0]++;if(kind==='affine')draft.source.affine[0][3]++;
  assert.throws(()=>validateAnnotationDraft(draft,source));
});
for (const kind of ['unknown','negative','nan','infinity','reference_zero','range','outside','duplicates','percentage_basis','reference_reason']) test(`draft refuses malformed worksheet ${kind}`,()=>{
  const {source,draft}=draftWithWorksheet(),row=draft.proposed_lesions[0];
  if(kind==='unknown')row.validated=true;if(kind==='negative')row.minimum_lumen_diameter_mm=-1;
  if(kind==='nan')row.minimum_lumen_diameter_mm=NaN;if(kind==='infinity')row.minimum_lumen_diameter_mm=Infinity;
  if(kind==='reference_zero')row.adjacent_reference_diameter_mm=0;if(kind==='range')row.percentage_narrowing=101;
  if(kind==='outside')row.center_ijk=[20,0,0];if(kind==='duplicates')draft.proposed_lesions.push(structuredClone(row));
  if(kind==='percentage_basis')row.percentage_narrowing=0;if(kind==='reference_reason')row.adjacent_reference_diameter_mm=1;
  assert.throws(()=>annotationDraftBlob(draft,source));
});
test('manual zero and unavailable values remain distinct in an unverified draft',async()=>{
  const {source,draft}=draftWithWorksheet(),row=draft.proposed_lesions[0];
  row.minimum_lumen_diameter_mm=0;row.percentage_narrowing=0;row.percentage_basis='Software guard test only; not a clinical label';
  const value=JSON.parse(await annotationDraftBlob(draft,source).text());assert.equal(value.proposed_lesions[0].minimum_lumen_diameter_mm,0);
  assert.equal(value.proposed_lesions[0].adjacent_reference_diameter_mm,null);assert.equal(value.clinical_validation,false);
});
test('dedicated draft export checks toJSON snapshot and does not mutate input',async()=>{
  const {source,draft}=draftWithWorksheet(),before=structuredClone(draft);
  await annotationDraftBlob(draft,source).text();assert.deepEqual(draft,before);
  Object.defineProperty(draft,'toJSON',{value:()=>({...before,clinical_validation:true})});
  assert.throws(()=>annotationDraftBlob(draft,source));
});
test('both ordinary JSON report boundaries reject draft wrappers and extracted worksheets',()=>{
  const {draft}=draftWithWorksheet();
  for (const value of [draft,draft.proposed_lesions[0],{nested:{draft}}]) {
    assert.throws(()=>reportJsonBlob({result:value}),/annotation drafts/);
    assert.throws(()=>downloadRecords([{id:1,notes:value}],'json'),/annotation drafts/);
  }
});

test('CT-only private review notes are excluded by both normal JSON export paths',()=>{
  const note={schema_version:'ct-review-note/0.1',notes:'Unverified synthetic preparation',
    clinical_gate_authorized:false,training_release_authorized:false};
  for(const value of [note,{nested:[note]}]) {
    assert.throws(()=>reportJsonBlob({result:value}),/annotation drafts/);
    assert.throws(()=>downloadRecords([{id:1,notes:value}],'json'),/annotation drafts/);
  }
});

for (const field of ['reference_diameter','minimum_lumen_diameter','percentage_narrowing']) test(`report rejects unvalidated numeric ${field} before print or JSON presentation`, async () => {
  const report = await reportFixture();
  report.result.result.lesions[0].measurements[field] = {value:0,unit:field==='percentage_narrowing'?'percent':'mm',
    unavailable_reason:null,method_id:'synthetic-test-only',method_version:'v1',definition:'Negative gate bypass fixture'};
  await assert.rejects(validateReport(report,1,report.analysis.analysis_id), /validated quantitative/);
});

test('server-derived zero and populated summaries preserve unavailable metrics',()=>{
  for(const populated of [false,true]){const data=summaryFixture({populated});assert.equal(validateSummary(data),data);assert.equal(data.severity_distribution,null);}
});
for(const kind of ['missing','sum','quality','missing_measurements','unknown_severity','patients'])test(`malformed analytics ${kind} is not a zero success`,()=>{
  const data=summaryFixture({populated:true});if(kind==='missing')delete data.jobs;if(kind==='sum')data.jobs.total=99;if(kind==='quality')data.quality.unverified=99;if(kind==='missing_measurements')data.measurements.pop();if(kind==='unknown_severity')data.severity_distribution=[];if(kind==='patients')data.current.unique_patients='unknown';
  assert.throws(()=>validateSummary(data));
});
test('index identity and pagination are checked',()=>{assert.ok(validateIndex(indexFixture({populated:true})));const data=indexFixture();data.has_more=true;assert.throws(()=>validateIndex(data));});
for(const state of ['completed','failed','queued','running','stale','integrity_error'])test(`typed ${state} report preserves findings availability`,async()=>{
  const report=await reportFixture({state});assert.equal(await validateReport(report,1,report.analysis.analysis_id),report);if(state!=='completed')assert.equal(report.result,null);
});
test('zero-finding completed report remains a genuine typed result',async()=>{const report=await reportFixture({count:0});await validateReport(report,1,report.analysis.analysis_id);assert.equal(report.result.result.lesions.length,0);});
test('cross-case and fabricated completed reports fail closed',async()=>{
  const report=await reportFixture();await assert.rejects(validateReport(report,2,report.analysis.analysis_id));report.result=null;await assert.rejects(validateReport(report,1,report.analysis.analysis_id));
});
test('shared authenticated adapter passes filters and cancellation without deriving counts',async()=>{
  const calls=[],controller=new AbortController(),data=summaryFixture();const api=createStenosisReportingApi({get:async(...args)=>{calls.push(args);return{status:200,data};}});
  await api.analytics({case_id:1,status:'completed'},{signal:controller.signal});assert.deepEqual(calls,[[ '/cases/1/stenosis/analytics',{params:{case_id:1,status:'completed'},signal:controller.signal} ]]);
});
test('HTTP errors stay errors and Blob error bodies never download as CSV',async()=>{
  const report=await reportFixture(),failure=Object.assign(new Error('HTTP 409'),{response:{data:new Blob([JSON.stringify({detail:{contract_version:'1.0',code:'source_changed',message:'Source changed'}})],{type:'application/json'})}});
  const api=createStenosisReportingApi({get:async()=>{throw failure;}});
  await assert.rejects(api.reportCsv(1,report.analysis.analysis_id),{code:'source_changed',message:'Source changed'});
  await assert.rejects(createStenosisReportingApi({get:async()=>({status:200,data:new Blob(['<html>'],{type:'text/html'})})}).reportCsv(1,report.analysis.analysis_id),/CSV findings/);
});
test('versioned JSON export allowlists top-level report fields',async()=>{
  const report=await reportFixture();report.worker_token='must not export';const body=JSON.parse(await reportJsonBlob(report).text());assert.equal(body.schema_version,'1.0');assert.equal(body.worker_token,undefined);assert.equal(body.result.result.lesions.length,3);
});

test('report identifiers use the same UUID case semantics as jobs and results',async()=>{
  const report=await reportFixture(),canonical=report.analysis.analysis_id,upper=canonical.toUpperCase();
  assert.notEqual(upper,canonical);
  assert.equal(await validateReport(report,1,upper),report);
  const paths=[];
  const api=createStenosisReportingApi({get:async path=>{paths.push(path);return {status:200,data:report};}});
  await api.report(1,upper);
  assert.deepEqual(paths,[`/cases/1/stenosis/analyses/${canonical}/report`]);
});

test('unavailable measurements preserve independently optional method metadata',async()=>{
  for(const field of ['method_id','method_version']){
    const report=await reportFixture(),measurement=report.result.result.lesions[0].measurements.reference_diameter;
    measurement[field]='supplied-optional';
    assert.equal(measurement.value,null);
    assert.equal(await validateReport(report,1,report.analysis.analysis_id),report);
    measurement[field]='invalid method with spaces';
    await assert.rejects(validateReport(report,1,report.analysis.analysis_id));
  }
});

function unbackedMeasurement(field, value = 37) {
  return {value,unit:field==='percentage_narrowing'?'percent':'mm',unavailable_reason:null,
    method_id:'synthetic-negative-export',method_version:'v1',definition:'Unvalidated synthetic export fixture'};
}

for (const field of ['reference_diameter','minimum_lumen_diameter','percentage_narrowing']) {
  for (const value of [0,37]) test(`direct JSON export rejects unbacked ${field}=${value} without mutating input`,async()=>{
    const report=await reportFixture();
    report.result.result.lesions[0].measurements[field]=unbackedMeasurement(field,value);
    const before=structuredClone(report);
    assert.throws(()=>reportJsonBlob(report),/validated quantitative/);
    assert.deepEqual(report,before);
  });
}

for (const claim of ['flag','id','hash','all']) test(`direct JSON export rejects forged ${claim} claims`,async()=>{
  const report=await reportFixture(),measurement=unbackedMeasurement('percentage_narrowing');
  if (claim==='flag'||claim==='all') measurement.validated=true;
  measurement.validation_gate={
    gate_id:claim==='id'?'__proto__':'synthetic-unregistered',gate_version:'v1',
    evidence_sha256:'a'.repeat(64),source_sha256:report.result.result.provenance.source.source_sha256,
    analysis_method_id:report.result.result.provenance.method_id,
    analysis_method_version:report.result.result.provenance.method_version,checkpoint_sha256:null,
    validated:true,
  };
  report.result.result.lesions[0].measurements.percentage_narrowing=measurement;
  assert.throws(()=>reportJsonBlob(report),/validated quantitative/);
});

for (const shape of ['raw-result','response','nested-report','array']) test(`direct JSON export protects ${shape} measurements`,async()=>{
  const report=await reportFixture(),response=report.result;
  response.result.lesions.at(-1).measurements.minimum_lumen_diameter=unbackedMeasurement('minimum_lumen_diameter',0);
  if (shape==='raw-result') report.result=response.result;
  if (shape==='nested-report') report.result={cached:{report:{result:response}}};
  if (shape==='array') report.result={history:[{result:null},{result:response}]};
  assert.throws(()=>reportJsonBlob(report),/validated quantitative/);
});

test('JSON export rechecks a cached report mutated after successful API validation',async()=>{
  const report=await reportFixture();
  await validateReport(report,1,report.analysis.analysis_id);
  report.result.result.lesions[0].measurements.percentage_narrowing.value=37;
  const before=structuredClone(report);
  assert.throws(()=>reportJsonBlob(report),/validated quantitative/);
  assert.deepEqual(report,before);
});

test('JSON export preserves null measurements, reasons and the original report',async()=>{
  const report=await reportFixture(),before=structuredClone(report);
  const blob=reportJsonBlob(report),body=JSON.parse(await blob.text());
  assert.equal(blob.type,'application/json;charset=utf-8');
  assert.deepEqual(body,before);
  assert.deepEqual(report,before);
  assert.equal(body.result.result.lesions[0].measurements.percentage_narrowing.value,null);
});

test('unavailable reports with no result remain exportable',async()=>{
  const report=await reportFixture({state:'failed'});
  assert.deepEqual(JSON.parse(await reportJsonBlob(report).text()),report);
});

test('JSON export preserves segmentation/evaluation zeros and unrelated percentages',async()=>{
  const report=await reportFixture();
  report.result={segmentation:{metrics:{dice:0,iou:0,precision:0,recall:0}},
    evaluations:[{macro:{dice:0,iou:0,precision:0,recall:0},pooled:{tp:0,fp:0,fn:0}}],
    measurements:{percentage_change:0},percentage:0,percentage_narrowing:0};
  assert.deepEqual(JSON.parse(await reportJsonBlob(report).text()),report);
});

test('ordinary unrelated JSON retains the existing allowlist and formatting',async()=>{
  const report={schema_version:'1.0',document_type:'unrelated-synthetic',generated_at:'2026-11-12T00:00:00Z',
    case:{case_id:0},analysis:{duration:0},report_state:'empty',unavailable_reason:null,
    result:{count:0,percentage:37,items:[false,null,'example']},explanations:null,limitations:[]};
  const before=structuredClone(report);
  assert.equal(await reportJsonBlob(report).text(),JSON.stringify(before,null,2));
  assert.deepEqual(report,before);
});

test('JSON export validates serialized toJSON output rather than a different source object',async()=>{
  const report=await reportFixture(),lesion=report.result.result.lesions[0];
  lesion.measurements.percentage_narrowing.toJSON=()=>unbackedMeasurement('percentage_narrowing');
  assert.throws(()=>reportJsonBlob(report),/validated quantitative/);
});

test('JSON export checks and emits the same snapshot without rereading getters',async()=>{
  const report=await reportFixture(),measurement=report.result.result.lesions[0].measurements.percentage_narrowing;
  let reads=0;
  Object.defineProperty(measurement,'value',{enumerable:true,get:()=>++reads===1?null:37});
  const body=JSON.parse(await reportJsonBlob(report).text());
  assert.equal(reads,1);
  assert.equal(body.result.result.lesions[0].measurements.percentage_narrowing.value,null);
});

for (const value of [NaN,Infinity,-Infinity]) test(`JSON export does not coerce ${value} into a valid unavailable measurement`,async()=>{
  const report=await reportFixture();
  report.result.result.lesions[0].measurements.percentage_narrowing=unbackedMeasurement('percentage_narrowing',value);
  assert.throws(()=>reportJsonBlob(report),/explicit reason/);
});

function captureDownloads(t) {
  const blobs=[],links=[],descriptor=Object.getOwnPropertyDescriptor(globalThis,'document');
  t.mock.method(URL,'createObjectURL',blob=>{blobs.push(blob);return 'blob:synthetic-export';});
  t.mock.method(URL,'revokeObjectURL',()=>{});
  t.mock.method(globalThis,'setTimeout',callback=>{callback();return 0;});
  Object.defineProperty(globalThis,'document',{configurable:true,value:{createElement:()=>{
    const link={click(){links.push(this);}};return link;
  }}});
  t.after(()=>{if(descriptor)Object.defineProperty(globalThis,'document',descriptor);else delete globalThis.document;});
  return {blobs,links};
}

test('research workflow download retains bound reviewer provenance without mutation or clinical claims',async t=>{
  const {blobs,links}=captureDownloads(t),data=workflowFixture({reviewed:true}),before=structuredClone(data);
  data.private_path='must not export';data.review.private_path='must not export';
  const input=structuredClone(data);
  downloadCaseWorkflow(data);
  const body=JSON.parse(await blobs[0].text());
  assert.equal(links.length,1);assert.equal(body.document_type,'research_case_workflow');
  assert.equal(body.clinical_validation,false);assert.equal(body.workflow.review.reviewer_id,1);
  assert.equal(body.workflow.review.scope,'research_workflow_v1');assert.deepEqual(data,input);
  assert.equal(body.workflow.private_path,undefined);assert.equal(body.workflow.review.private_path,undefined);
  assert.equal(body.workflow.review.id,before.review.id);
});
test('workflow export validates serialized snapshot claims before creating a Blob',t=>{
  const {blobs}=captureDownloads(t),data=workflowFixture();
  data.toJSON=()=>({...workflowFixture(),clinical_validation:true});
  assert.throws(()=>downloadCaseWorkflow(data),/inconsistent/);assert.equal(blobs.length,0);
});
for(const value of [0,37])test(`workflow JSON export also refuses unbacked stenosis ${value} before any Blob`,async t=>{
  const {blobs,links}=captureDownloads(t),report=await reportFixture(),data=workflowFixture();
  report.result.result.lesions[0].measurements.percentage_narrowing=unbackedMeasurement('percentage_narrowing',value);
  data.cached=report;
  assert.throws(()=>downloadCaseWorkflow(data),/validated quantitative/);
  assert.equal(blobs.length,0);assert.equal(links.length,0);
});

test('alternate case JSON download enforces the same nested measurement guard before creating a download',async t=>{
  const {blobs,links}=captureDownloads(t),report=await reportFixture();
  report.result.result.lesions[0].measurements.percentage_narrowing=unbackedMeasurement('percentage_narrowing');
  const items=[{id:1,notes:{cached:report}}],before=structuredClone(items);
  assert.throws(()=>downloadRecords(items,'json'),/validated quantitative/);
  assert.deepEqual(blobs,[]);
  assert.deepEqual(links,[]);
  assert.deepEqual(items,before);
});

test('ordinary case JSON download preserves zero values, allowlisting and input',async t=>{
  const {blobs,links}=captureDownloads(t),items=[{id:1,caseCode:'SYNTHETIC-CASE',age:0,notes:'Synthetic metadata only',private_path:'must not export'}];
  const before=structuredClone(items);
  downloadRecords(items,'json');
  assert.equal(links.length,1);
  const body=JSON.parse(await blobs[0].text());
  assert.equal(body.document_type,'research_case_metadata');
  assert.equal(body.cases[0].age_years,0);
  assert.equal(body.cases[0].notes,items[0].notes);
  assert.equal(body.cases[0].private_path,undefined);
  assert.deepEqual(items,before);
});

for (const wrapper of ['result','notes-array','case-metadata','candidate-only','serialized-wrapper']) test(`ordinary report JSON refuses experimental ${wrapper} before Blob creation`,async t=>{
  const {preview}=await loadExperimentalFixture(),report=await reportFixture();
  if(wrapper==='result')report.result=preview;
  if(wrapper==='notes-array')report.result={retained:{notes:[{metadata:{preview}}]}};
  if(wrapper==='case-metadata')report.case.metadata={preview};
  if(wrapper==='candidate-only')report.result={items:[preview.candidates[0]]};
  if(wrapper==='serialized-wrapper')report.result={toJSON:()=>({preview})};
  const before=wrapper==='serialized-wrapper'?null:structuredClone(report);
  let blobs=0;
  t.mock.method(globalThis,'Blob',function ForbiddenBlob(){blobs++;throw new Error('Blob must not be created');});
  assert.throws(()=>reportJsonBlob(report),/Experimental candidate previews cannot be included in ordinary reports or metadata exports/);
  assert.equal(blobs,0);
  if(before)assert.deepEqual(report,before);
});

for (const wrapper of ['preview','metadata','notes-array','candidate-only']) test(`ordinary case metadata JSON refuses experimental ${wrapper} before Blob/URL/download`,async t=>{
  const {preview}=await loadExperimentalFixture(),{blobs,links}=captureDownloads(t);
  const notes=wrapper==='preview'?preview:wrapper==='metadata'?{metadata:{preview}}:wrapper==='candidate-only'?[preview.candidates[0]]:{notes:[{preview}]};
  const items=[{id:1,caseCode:'SYNTHETIC-ONLY',notes}],before=structuredClone(items);
  let constructors=0;
  t.mock.method(globalThis,'Blob',function ForbiddenBlob(){constructors++;throw new Error('Blob must not be created');});
  assert.throws(()=>downloadRecords(items,'json'),/Experimental candidate previews cannot be included in ordinary reports or metadata exports/);
  assert.equal(constructors,0);assert.deepEqual(blobs,[]);assert.deepEqual(links,[]);assert.deepEqual(items,before);
});

test('standalone research-preview JSON remains usable without entering ordinary exports',async()=>{
  const f=await loadExperimentalFixture(),before=structuredClone(f.preview);
  const standalone=JSON.parse(JSON.stringify(f.preview,null,2));
  assert.equal(standalone.schema_version,'experimental-candidates/1.0');
  assert.ok(standalone.candidates.length>0);
  assert.deepEqual(await validateExperimentalPreview(standalone,f.geometry,f.segmentation,f.verifiedMask),before);
  assert.deepEqual(f.preview,before);
});

test('ordinary JSON still preserves unrelated experimental wording and genuine evaluation zeros',async()=>{
  const report=await reportFixture();
  report.result={schema_version:'ordinary-metadata/1.0',kind:'experimental_candidate_note',percentage:0,
    metrics:{dice:0,iou:0,precision:0,recall:0},notes:['experimental candidate previews are unavailable']};
  assert.deepEqual(JSON.parse(await reportJsonBlob(report).text()),report);
});

for(const version of ['review-adjudication/0.1','review-adjudication-version/0.1',null])test(`ordinary JSON rejects unverified adjudication ${version||'without tag'} through both public exports`,async t=>{
  const record={r1_submission_sha256:'a'.repeat(64),r2_submission_sha256:'b'.repeat(64),correspondences:[],resolutions:[],
    ...(version?{schema_version:version}:{}),clinical_gate_authorized:false,training_release_authorized:false};
  const report=await reportFixture();report.result={review:record};const before=structuredClone(report);let blobs=0;
  t.mock.method(globalThis,'Blob',function ForbiddenBlob(){blobs++;throw new Error('No Blob before validation');});
  assert.throws(()=>reportJsonBlob(report),/Unverified/);
  assert.throws(()=>downloadRecords([{id:1,caseCode:'SYNTHETIC-ONLY',notes:record}],'json'),/Unverified/);
  assert.equal(blobs,0);assert.deepEqual(report,before);
});

test('abstained automatic branch research evidence cannot enter either ordinary JSON path',async t=>{
  // Contract sentinel only: no centerline experiment or medical data is created.
  const research={schema_version:'experimental-automatic-candidates/0.1',status:'abstained',preview:null,
    measurement_status:'measurement_unavailable_no_validated_gate',graph:{status:'abstained'}};
  const report=await reportFixture();report.result={research};let blobs=0;
  t.mock.method(globalThis,'Blob',function ForbiddenBlob(){blobs++;throw new Error('No Blob before validation');});
  assert.throws(()=>reportJsonBlob(report),/Experimental candidate previews/);
  assert.throws(()=>downloadRecords([{id:1,caseCode:'SYNTHETIC-ONLY',notes:{research}}],'json'),/Experimental candidate previews/);
  assert.equal(blobs,0);
});
