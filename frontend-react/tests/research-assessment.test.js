import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { gunzipSync } from 'node:zlib';
import { loadExperimentalFixture } from './experimental-candidates-fixtures.js';
import { experimentalMaskIdentity } from '../src/lib/experimental-candidates.js';
import { blankResearchCalipers, canonicalResearchJson, createResearchAssessment, researchAssessmentBlob,
  researchCalipers, validateResearchAssessment } from '../src/lib/research-assessment.js';
import { downloadRecords, reportJsonBlob } from '../src/lib/exports.js';
import {evidenceLineSegments,researchEvidenceRows} from '../src/lib/research-evidence.js';

async function setup(variant='preview') {
  const f=await loadExperimentalFixture('flipped',variant);
  return {preview:f.preview,context:{geometry:f.geometry,segmentation:f.segmentation,mask:f.verifiedMask}};
}
test('actual extractor fixture produces two distinct procedures and hash-linked R3 without invented labels',async()=>{
  const {preview,context}=await setup(),before=structuredClone(preview);
  const value=await createResearchAssessment(preview,context),doc=value.document;
  assert.deepEqual(doc.records.map(row=>row.record.role),['R1','R2','R3']);
  assert.notEqual(doc.records[0].record.procedure,doc.records[1].record.procedure);
  assert.deepEqual(doc.records[2].record.parent_sha256,doc.records.slice(0,2).map(row=>row.sha256));
  assert.equal(doc.records[0].record.evidence[0].proposals.length,preview.candidates.length);
  const candidate=doc.records[0].record.evidence[0].proposals[0];
  assert.deepEqual(candidate.center_ijk,preview.candidates[0].sample_ijk);
  assert.deepEqual(candidate.interval_s_mm,preview.candidates[0].interval_s_mm);
  assert.equal(candidate.artery,null);assert.equal(candidate.confidence,null);
  assert.equal(candidate.research_measurement.severity_category,null);
  assert.equal(doc.model_provenance.checkpoint_sha256,null);
  assert.equal(doc.model_provenance.assessment_model,null);
  assert.equal(doc.attribution.map,null);
  for(const row of doc.records) {
    assert.equal(row.record.clinical_gate_authorized,false);assert.equal(row.record.training_release_authorized,false);
    assert.equal(row.record.qualified_human_reviewer,false);assert.equal(row.record.reviewer_independence_verified,false);
    assert.match(row.sha256,/^[a-f0-9]{64}$/);
  }
  assert.ok(Object.isFrozen(value)&&Object.isFrozen(doc.records[0].record.evidence[0].proposals));
  assert.throws(()=>{candidate.artery='invented';},TypeError);
  assert.deepEqual(preview,before);
});
test('each R2 reference is independently computed as the smaller directional mean',async()=>{
  const {preview,context}=await setup(),doc=(await createResearchAssessment(preview,context)).document;
  for(const [b,branch] of preview.branches.entries())for(const [i,row] of branch.sections.entries()) {
    if(row.status!=='evaluable_candidate_only')continue;
    const p=preview.parameters;
    const means=[-1,1].map(sign=>branch.sections.filter(other=>(other.s_mm-row.s_mm)*sign>=p.reference_inner_mm
      &&(other.s_mm-row.s_mm)*sign<=p.reference_outer_mm).map(r=>r.diagnostic_area_mm2)).map(a=>a.reduce((s,n)=>s+n,0)/a.length);
    assert.equal(doc.records[1].record.evidence[b].sections[i].reference_area_mm2,Math.min(...means));
  }
});

const boundaries=JSON.parse(readFileSync(new URL('./fixtures/research-procedure-boundaries.json',import.meta.url),'utf8')).variants;
for(const [name,profile] of Object.entries(boundaries))test(`actual backend boundary evidence is replayable: ${name}`,async()=>{
  const {context}=await setup();
  const first=await createResearchAssessment(profile,context),again=await createResearchAssessment(profile,context);
  assert.equal(first.sha256,again.sha256);
  const doc=first.document,r1=doc.records[0].record.evidence[0];
  assert.equal(r1.proposals.length,profile.candidates.length);
  assert.deepEqual(r1.proposals.map(row=>row.interval_s_mm),profile.candidates.map(row=>row.interval_s_mm));
  for(const [i,row] of profile.branches[0].sections.entries()) {
    const one=r1.sections[i],two=doc.records[1].record.evidence[0].sections[i];
    assert.equal(one.s_mm,i*profile.parameters.sample_step_mm);
    if(row.status==='evaluable_candidate_only') {
      assert.equal(one.proposed,row.diagnostic_area_mm2<=one.reference_area_mm2*profile.parameters.area_ratio_trigger);
      const left=profile.branches[0].sections.filter(r=>row.s_mm-r.s_mm>=profile.parameters.reference_inner_mm && row.s_mm-r.s_mm<=profile.parameters.reference_outer_mm);
      const right=profile.branches[0].sections.filter(r=>r.s_mm-row.s_mm>=profile.parameters.reference_inner_mm && r.s_mm-row.s_mm<=profile.parameters.reference_outer_mm);
      const mean=rows=>rows.reduce((n,r)=>n+r.diagnostic_area_mm2,0)/rows.length;
      assert.equal(two.reference_area_mm2,Math.min(mean(left),mean(right)));
    } else {assert.equal(one.reference_area_mm2,null);assert.equal(two.proposed,false);}
  }
  if(name==='inclusive_threshold')assert.ok(r1.proposals.length>0);
  if(name==='below_threshold'||name==='contiguous_six')assert.equal(r1.proposals.length,0);
  if(name==='insufficient_support')assert.equal(r1.evaluable_sections,0);
});
test('visual evidence retains source coordinates, inclusive support windows, calculation values and accepted-region membership',async()=>{
  const {preview,context}=await setup(),value=await createResearchAssessment(preview,context),rows=researchEvidenceRows(value,'main');
  assert.equal(rows.length,preview.branches[0].sections.length);
  for(const [i,row]of rows.entries()) {
    const raw=preview.branches[0].sections[i],r1=value.document.records[0].record.evidence[0].sections[i];
    assert.deepEqual(row.sample_ijk,raw.sample_ijk);assert.deepEqual(row.world_ras_mm,raw.world_ras_mm);
    assert.deepEqual(row.left_window_mm,[raw.s_mm-preview.parameters.reference_outer_mm,raw.s_mm-preview.parameters.reference_inner_mm]);
    assert.equal(row.sampled_area_mm2,raw.diagnostic_area_mm2);
    assert.equal(row.r1_trigger_area_mm2,r1.reference_area_mm2===null?null:r1.reference_area_mm2*preview.parameters.area_ratio_trigger);
  }
  const central=rows.find(row=>row.r1_regions.length);assert.ok(central);assert.equal(central.r1_raw_trigger,true);
  assert.throws(()=>researchEvidenceRows(value,'wrong'),/mismatch/);
});
test('visual reference curves never bridge unavailable samples',()=>{
  const rows=[{s_mm:0,a:1},{s_mm:1,a:null},{s_mm:2,a:3},{s_mm:3,a:4}];
  assert.deepEqual(evidenceLineSegments(rows,'a'),[[[0,1]],[[2,3],[3,4]]]);
  assert.throws(()=>evidenceLineSegments([{s_mm:0,a:NaN}],'a'),/Invalid/);
});
test('derived section evidence and full-volume wrappers cannot enter either normal JSON path',async()=>{
  const {preview,context}=await setup(),value=await createResearchAssessment(preview,context);
  const rows=researchEvidenceRows(value,'main'),full={schema_version:'full-volume-research-profile/0.1',profile:preview};
  for(const input of [rows,rows[0],full]) {
    assert.throws(()=>reportJsonBlob({result:{nested:input}}),/research/);
    assert.throws(()=>downloadRecords([{id:1,notes:input}],'json'),/research/);
  }
});
test('oblique anisotropic caliper distances use independently known physical displacements; shear and conflicting units refuse',()=>{
  const c=Math.SQRT1_2,g={shape:[20,20,20],units:'mm',affine:[[2*c,-3*c,0,10],[2*c,3*c,0,-5],[0,0,4,7],[0,0,0,1]]};
  assert.ok(Math.abs(researchCalipers(calipers(),g).minimum_diameter_mm-2)<1e-12);
  g.affine[0][0]=.2;assert.throws(()=>researchCalipers(calipers(),g),/Sheared/);
  const conflict={...geometry,world_unit:'m'};assert.throws(()=>researchCalipers(calipers(),conflict),/Conflicting/);
});
for(const change of ['version','procedure','incomplete','sampling','model_metadata'])test(`standalone restore rejects altered ${change}`,async()=>{
  const {preview,context}=await setup(),value=structuredClone(await createResearchAssessment(preview,context));
  if(change==='version')value.document.records[1].record.procedure_version='forged';
  if(change==='procedure')value.document.records[1].record.procedure='majority_vote';
  if(change==='incomplete')value.document.records.pop();
  if(change==='sampling')value.document.profile.branches[0].sections[10].s_mm+=.5;
  if(change==='model_metadata')value.document.model_provenance.threshold=.3;
  await assert.rejects(()=>validateResearchAssessment(value,context));
});
test('asymmetric actual backend evidence produces real procedural disagreement and retains both proposal lists',async()=>{
  const bundle=JSON.parse(readFileSync(new URL('./fixtures/research-asymmetric-profile.json',import.meta.url),'utf8'));
  const mask=gunzipSync(Buffer.from(bundle.mask_gzip_base64,'base64'));
  const preview=bundle.preview,context={geometry:preview.geometry,
    segmentation:{id:preview.source.parent_segmentation_result_id,case_id:1,stale:false,metadata:{source_sha256:preview.source.source_sha256}},
    mask:await experimentalMaskIdentity(mask.buffer.slice(mask.byteOffset,mask.byteOffset+mask.byteLength),preview.geometry.shape)};
  const doc=(await createResearchAssessment(preview,context)).document;
  const r1=doc.records[0].record.evidence[0],r2=doc.records[1].record.evidence[0],third=doc.records[2].record.evidence[0];
  assert.ok(r1.proposals.length>0);assert.equal(r2.proposals.length,0);
  assert.ok(third.sections.some(row=>row.status==='disagreement_unresolved'));
  assert.deepEqual(third.r1_proposal_ids,r1.proposals.map(row=>row.proposal_id));
  assert.deepEqual(third.r2_proposal_ids,[]);
  assert.equal(doc.records[2].record.adjudication_status,'provisional_comparison_not_clinical_adjudication');
});
for(const variant of ['no_candidate_preview','abstained_preview'])test(`${variant} preserves unassessable coverage and does not report normal anatomy`,async()=>{
  const {preview,context}=await setup(variant),doc=(await createResearchAssessment(preview,context)).document;
  assert.equal(doc.records[0].record.evidence.flatMap(b=>b.proposals).length,0);
  assert.equal(doc.manual_caliper_result.minimum_diameter_mm,null);
  assert.equal(doc.manual_caliper_result.diagnostic_diameter_reduction_percent,null);
  assert.ok(doc.records[2].record.evidence.every(b=>b.sections.every(row=>['unassessable','no_trigger_not_normal'].includes(row.status))));
});
for(const kind of ['ct','mask_hash','mask_bytes','geometry','case','stale','reference_role','forged_confidence','checkpoint','threshold'])test(`source validation rejects ${kind}`,async()=>{
  const {preview,context}=await setup();
  if(kind==='ct')context.segmentation.metadata.source_sha256='f'.repeat(64);
  if(kind==='mask_hash')context.mask.sha256='f'.repeat(64);
  if(kind==='mask_bytes')context.mask.labels[0]=1-context.mask.labels[0];
  if(kind==='geometry')context.geometry.affine[0][3]+=1;
  if(kind==='case')context.segmentation.case_id=0;
  if(kind==='stale')context.segmentation.stale=true;
  if(kind==='reference_role')preview.source.mask_role='reference_annotation';
  if(kind==='forged_confidence')preview.candidates[0].confidence=.99;
  if(kind==='checkpoint')context.segmentation.metadata.checkpoint_sha256='invalid';
  if(kind==='threshold')context.segmentation.metadata.threshold=Infinity;
  await assert.rejects(()=>createResearchAssessment(preview,context));
});
test('reproducible restore and standalone export revalidate against current source',async()=>{
  const {preview,context}=await setup(),value=await createResearchAssessment(preview,context);
  assert.equal(canonicalResearchJson(await createResearchAssessment(preview,context)),canonicalResearchJson(value));
  const blob=await researchAssessmentBlob(value,context);
  assert.deepEqual(await validateResearchAssessment(JSON.parse(await blob.text()),context),value);
  context.segmentation.metadata.source_sha256='f'.repeat(64);
  await assert.rejects(()=>researchAssessmentBlob(value,context));
});
for(const kind of ['clinical_flag','training_flag','r1','r2','r3_parent','outer_hash','model','manual','extra_field'])test(`restore rejects altered ${kind}, even with supplied hash claims`,async()=>{
  const {preview,context}=await setup(),value=structuredClone(await createResearchAssessment(preview,context));
  if(kind==='clinical_flag')value.document.clinical_gate_authorized=true;
  if(kind==='training_flag')value.document.records[2].record.training_release_authorized=true;
  if(kind==='r1')value.document.records[0].record.evidence[0].proposals=[];
  if(kind==='r2')value.document.records[1].record.evidence[0].sections[10].proposed=true;
  if(kind==='r3_parent')value.document.records[2].record.parent_sha256[0]='f'.repeat(64);
  if(kind==='outer_hash')value.sha256='f'.repeat(64);
  if(kind==='model')value.document.model_provenance.assessment_model='made-up-expert';
  if(kind==='manual')value.document.manual_caliper_result.minimum_diameter_mm=0;
  if(kind==='extra_field')value.document.validated=true;
  await assert.rejects(()=>validateResearchAssessment(value,context));
});
const geometry={shape:[20,20,20],units:'mm',affine:[[-2,0,0,50],[0,3,0,-20],[0,0,4,7],[0,0,0,1]]};
const calipers=()=>({minimum_start_ijk:[1,1,1],minimum_end_ijk:[2,1,1],reference_start_ijk:[1,2,1],reference_end_ijk:[3,2,1],method_evidence:'Synthetic transverse plane; adjacent reference selected for arithmetic test only.'});
test('caliper arithmetic uses physical anisotropic coordinates and preserves genuine zero reduction',()=>{
  const input=calipers(),before=structuredClone(input),row=researchCalipers(input,geometry);
  assert.equal(row.minimum_diameter_mm,2);assert.equal(row.reference_diameter_mm,4);assert.equal(row.diagnostic_diameter_reduction_percent,50);
  assert.equal(row.clinical_gate_authorized,false);assert.deepEqual(input,before);
  input.minimum_end_ijk=[3,1,1];assert.equal(researchCalipers(input,geometry).diagnostic_diameter_reduction_percent,0);
  input.minimum_end_ijk=[1,2,1];assert.equal(researchCalipers(input,geometry).minimum_diameter_mm,3);
});
for(const kind of ['singular','unknown_units','outside','nan','zero_length','missing_evidence','extra'])test(`caliper refuses invalid ${kind}`,()=>{
  const input=calipers(),g=structuredClone(geometry);
  if(kind==='singular')g.affine[0]=[0,0,0,0];if(kind==='unknown_units')g.units='unknown';
  if(kind==='outside')input.minimum_start_ijk=[20,1,1];if(kind==='nan')input.minimum_end_ijk=[NaN,1,1];
  if(kind==='zero_length')input.minimum_end_ijk=[1,1,1];if(kind==='missing_evidence')input.method_evidence='';if(kind==='extra')input.validated=true;
  assert.throws(()=>researchCalipers(input,g));
});
test('missing calipers and inverted reference remain unavailable instead of invented or clamped values',()=>{
  const blank=researchCalipers(blankResearchCalipers(),geometry);assert.equal(blank.minimum_diameter_mm,null);
  const input=calipers();input.minimum_end_ijk=[4,1,1];const row=researchCalipers(input,geometry);
  assert.equal(row.status,'unassessable');assert.equal(row.diagnostic_diameter_reduction_percent,null);
});
test('both ordinary JSON paths refuse whole or nested simulated outputs before creating a Blob',async()=>{
  const {preview,context}=await setup(),value=await createResearchAssessment(preview,context);
  const original=globalThis.Blob;let created=0;
  globalThis.Blob=class extends original {constructor(...args){created++;super(...args);}};
  try {
    const fragments=[value,value.document.records[0].record,value.document.records[0].record.evidence[0].proposals[0],value.document.manual_caliper_result];
    for(const nested of fragments)for(const call of [()=>downloadRecords([{id:1,notes:{nested}}],'json'),()=>reportJsonBlob({result:{nested}})])assert.throws(call,/research/);
    assert.equal(created,0);
  }finally{globalThis.Blob=original;}
});
