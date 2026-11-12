import test from 'node:test';
import assert from 'node:assert/strict';
import {createStenosisReportingApi,validateSummary,validateReport,validateIndex} from '../src/api/stenosis-reporting-contract.js';
import {downloadRecords,reportJsonBlob} from '../src/lib/exports.js';
import {summaryFixture,indexFixture,reportFixture} from './reporting-fixtures.js';

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
