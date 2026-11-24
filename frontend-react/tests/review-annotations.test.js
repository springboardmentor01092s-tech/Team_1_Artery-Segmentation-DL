import test from 'node:test';
import assert from 'node:assert/strict';
import {newReviewAnnotation,newReaderLesion,validateReviewAnnotation,reviewAnnotationBlob,manualNativeLandmark} from '../src/lib/review-annotation.js';
import {worldToNativeGeometry,POINT_FIELDS} from '../src/lib/annotation-draft.js';
import {reportJsonBlob,downloadRecords} from '../src/lib/exports.js';
import {reviewAnnotationsApi} from '../src/api/review-annotations.js';
import api from '../src/api/client.js';
const item={id:'11111111-1111-4111-8111-111111111111',protocol_version:'synthetic-unapproved',
 source:{case_id:1,source_sha256:'a'.repeat(64),shape:[5,7,9],affine:[[-2,0,0,10],[0,3,0,-4],[0,0,1,20],[0,0,0,1]],units:'mm'},geometry_identity:{version:'ct-geometry/1.0',sha256:'d'.repeat(64)}};

test('manual native coordinates preserve zero and fractional values without mutating source',()=>{
  const before=structuredClone(item.source);assert.deepEqual(manualNativeLandmark('0, 0, 0',item.source),[0,0,0]);
  assert.deepEqual(manualNativeLandmark('2.5 3 4',item.source),[2.5,3,4]);assert.deepEqual(item.source,before);
});
for(const text of ['', '1,2','1,2,NaN','Infinity 1 2','-1 2 3','5 2 3','0x1 2 3','1,,2,3',false])test(`manual native coordinates reject ${JSON.stringify(text)}`,()=>{
  assert.throws(()=>manualNativeLandmark(text,item.source));
});
test('manual entry validates singular geometry and all seven native landmark fields',()=>{
  const bad=structuredClone(item.source);bad.affine[0]=[0,0,0,0];assert.throws(()=>manualNativeLandmark('0 0 0',bad));
  const doc=newReviewAnnotation(item);doc.lesions=[newReaderLesion()];
  for(const field of POINT_FIELDS)doc.lesions[0][field]=manualNativeLandmark('2, 3, 4',item.source);
  validateReviewAnnotation(doc,item);assert.equal(doc.lesions[0].minimum_lumen_diameter_mm,null);assert.equal(doc.clinical_gate_authorized,false);
});
test('new reader worksheet contains no inferred clinical values or fabricated reader identity',async()=>{
  const doc=newReviewAnnotation(item);assert.deepEqual(doc.lesions,[]);assert.equal(doc.case_disposition,'not_assessed');
  assert.equal(doc.clinical_gate_authorized,false);assert.equal(doc.training_release_authorized,false);
  assert.equal(doc.reader_qualification_verified,false);assert.equal(doc.reader_independence_verified,false);
  validateReviewAnnotation(doc,item);assert.deepEqual(JSON.parse(await reviewAnnotationBlob(doc,item).text()),doc);
});
test('manual zero requires endpoints and explicit support; no percentage or severity is derived',()=>{
  const doc=newReviewAnnotation(item),row=newReaderLesion();doc.lesions=[row];doc.case_disposition='lesions_proposed';
  row.minimum_lumen_diameter_mm=0;assert.throws(()=>validateReviewAnnotation(doc,item));
  row.minimum_caliper_start_ijk=[1,1,1];row.minimum_caliper_end_ijk=[1,1,1];
  row.measurement_method='Synthetic test-only manual entry';row.measurement_evidence='Software fixture, not an expert annotation';
  validateReviewAnnotation(doc,item);assert.equal(row.percentage_narrowing,null);assert.equal(row.severity_category,null);
});
for(const field of POINT_FIELDS)test(`reader ${field} is checked against original native geometry`,()=>{
  const doc=newReviewAnnotation(item);doc.lesions=[newReaderLesion()];doc.lesions[0][field]=[5,0,0];
  assert.throws(()=>validateReviewAnnotation(doc,item));
  doc.lesions[0][field]=worldToNativeGeometry([6,5,24],item.source);assert.deepEqual(doc.lesions[0][field],[2,3,4]);
  validateReviewAnnotation(doc,item);
});
for(const kind of ['source','assignment','protocol','clinical_release','training_release','qualification','outside','percentage','severity','nonfinite'])test(`formal worksheet refuses ${kind} before JSON Blob creation`,()=>{
  const doc=newReviewAnnotation(item);doc.lesions=[newReaderLesion()];
  if(kind==='source')doc.source.source_sha256='b'.repeat(64);if(kind==='assignment')doc.assignment_id='22222222-2222-4222-8222-222222222222';
  if(kind==='protocol')doc.protocol_version='forged';if(kind==='clinical_release')doc.clinical_gate_authorized=true;
  if(kind==='training_release')doc.training_release_authorized=true;if(kind==='qualification')doc.reader_qualification_verified=true;
  if(kind==='outside')doc.lesions[0].center_ijk=[99,0,0];if(kind==='percentage')doc.lesions[0].percentage_narrowing=0;
  if(kind==='severity')doc.lesions[0].severity_category='mild';if(kind==='nonfinite')doc.lesions[0].center_ijk=[NaN,0,0];
  assert.throws(()=>reviewAnnotationBlob(doc,item));
});
test('normal report and metadata exports refuse nested formal worksheets',()=>{
  const doc=newReviewAnnotation(item),before=structuredClone(doc);
  assert.throws(()=>reportJsonBlob({result:{nested:doc}}),/Unverified annotation/);
  assert.throws(()=>downloadRecords([{id:1,notes:{nested:doc}}],'json'),/Unverified annotation/);
  assert.deepEqual(doc,before);
});
test('ordinary export also refuses immutable submission, amendment and adjudication containers',()=>{
  for(const schema_version of ['independent-review-submission/0.1','review-submission-amendment/0.1','review-adjudication/0.1']){
    const record={schema_version,clinical_gate_authorized:false,training_release_authorized:false};
    assert.throws(()=>reportJsonBlob({result:{record}}),/Unverified annotation/);
    assert.throws(()=>downloadRecords([{id:1,notes:{record}}],'json'),/Unverified annotation/);
  }
});

test('amendment client validates owner, parent hash, source and ordered hash links',async()=>{
  const doc=newReviewAnnotation(item),submissionHash='e'.repeat(64),recordHash='f'.repeat(64),documentHash='1'.repeat(64);
  const amendment={schema_version:'review-submission-amendment/0.1',id:'22222222-2222-4222-8222-222222222222',
    assignment_id:item.id,submission_id:'33333333-3333-4333-8333-333333333333',reviewer_id:7,revision:1,
    previous_id:null,previous_sha256:null,parent_submission_sha256:submissionHash,parent_annotation_revision:1,
    source:item.source,geometry_identity:item.geometry_identity,protocol_version:item.protocol_version,reason:'Synthetic test addendum',
    document_sha256:documentHash,document:doc,status:'unverified_addendum_original_submission_unchanged',recorded_at:'2026-11-24T00:00:00Z',
    clinical_gate_authorized:false,training_release_authorized:false};
  const row={id:amendment.id,revision:1,previous_id:null,previous_sha256:null,parent_submission_sha256:submissionHash,
    document_sha256:documentHash,record_sha256:recordHash,amendment,created_at:amendment.recorded_at};
  const original=api.get;api.get=async()=>({status:200,data:{schema_version:'review-amendment-history/0.1',assignment_id:item.id,
    submission_id:amendment.submission_id,submission_sha256:submissionHash,source_current:true,items:[row],revision:1,
    latest_sha256:recordHash,max_amendments:100,clinical_gate_authorized:false,training_release_authorized:false}});
  try{
    const result=await reviewAnnotationsApi.amendments(item,7);
    assert.equal(result.items[0].record_sha256,recordHash);
    const bad=structuredClone(amendment);bad.source.source_sha256='b'.repeat(64);
    api.get=async()=>({status:200,data:{schema_version:'review-amendment-history/0.1',assignment_id:item.id,
      submission_id:amendment.submission_id,submission_sha256:submissionHash,source_current:true,
      items:[{...row,amendment:bad}],revision:1,latest_sha256:recordHash,max_amendments:100,
      clinical_gate_authorized:false,training_release_authorized:false}});
    await assert.rejects(reviewAnnotationsApi.amendments(item,7),/does not match/);
  }finally{api.get=original;}
});
