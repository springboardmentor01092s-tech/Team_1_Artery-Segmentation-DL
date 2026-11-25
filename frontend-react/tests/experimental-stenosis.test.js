import test from 'node:test';
import assert from 'node:assert/strict';
import {createExperimentalStenosisApi} from '../src/api/experimental-stenosis.js';
import {validateSyntheticAnalysis,validateSyntheticSample,validateSyntheticStatus} from '../src/api/experimental-stenosis-contract.js';
import {analyzeRealVolumeResearch} from '../src/api/real-volume-research.js';
import {validateRealVolumeResearch} from '../src/api/real-volume-research-contract.js';

const hash='a'.repeat(64),sample={schema_version:'synthetic-stenosis-sample/0.2',sample_id:1,shape:[24,24,24],middle_slice_k:12,
  middle_slice:Array.from({length:24},()=>Array(24).fill(.1)),provenance:{source:'vascuai-synthetic-vessel-phantom',volume_sha256:hash},notice:'synthetic',clinical_validation:false,clinical_gate_authorized:false,training_release_authorized:false};
const analysis={schema_version:'experimental-stenosis-analysis/0.3',generated_at:'2026-11-25T00:00:00Z',status:'completed_synthetic_research_only',notice:'synthetic',
  provenance:{synthetic_sample_id:1,volume_sha256:hash,patient_case_id:null,dataset_case_id:null},
  geometry_analysis:{candidate_count:0,candidates:[],measurement_provenance:{scope:'synthetic_generated_phantom_only',input_volume_sha256:hash,method:'area-equivalent radius',axis_source:'generator-provided-synthetic-axis-not-automatically-extracted',provisional_severity_thresholds_percent:[10,30,50,70],clinical_gate_authorized:false,training_release_authorized:false},metrics:{reference_radius_synthetic_units:4,minimum_radius_synthetic_units:3,estimated_percentage_narrowing_synthetic_only:25,provisional_severity_synthetic_only:'mild',measurement_availability:'estimated_synthetic_profile_only',measurement_confidence:null,measurement_uncertainty:null,severity_thresholds_percent_synthetic_only:[10,30,50,70],area_profile_synthetic_units2:[1,2],position_profile_synthetic_units:[0,1]}},
  model:{model_id:'synthetic-3d-cnn',checkpoint_sha256:hash,clinical_performance_claim:false,score_semantics:'uncalibrated_softmax_probability_not_clinical_confidence',class_probabilities_uncalibrated:[.2,.2,.2,.2,.2]},
  explainability:{method:'3d-cnn-grad-cam',scope:'synthetic_generated_phantom_only',shape:[24,24,24],heatmap_values:Array(24**3).fill(0)},
  clinical_validation:false,clinical_gate_authorized:false,training_release_authorized:false};

test('valid synthetic sample, analysis and status contracts are accepted',()=>{
  assert.equal(validateSyntheticSample(sample),sample);
  assert.equal(validateSyntheticAnalysis(analysis),analysis);
  assert.equal(validateSyntheticStatus({available:false,reason:'checkpoint unavailable',scope:'synthetic_generated_phantoms_only',clinical_gate_authorized:false,training_release_authorized:false}).available,false);
});

const realVolumeResult={schema_version:'real-volume-research/0.1',status:'profile_only',notice:'real-volume QC only',
  provenance:{ct_sha256:hash,mask_file_sha256:'b'.repeat(64),persisted:false,synthetic_model_used:false},
  geometry:{shape_ijk:[32,32,32],orientation:['R','A','S'],ct_spatial_units:'mm',mask_spatial_units:'unknown',voxel_spacing_native:[.5,.5,1],voxel_spacing_mm:[.5,.5,1],affine_ras_mm:[],geometry_source:'CT NIfTI'},
  segmentation:{semantics:'supplied_coronary_artery_segmentation_unverified_lumen',foreground_voxels:64,component_count_26:1,component_voxel_counts_descending:[64],component_list_truncated:false},
  centerline:{status:'abstained',reasons:['source_loop_cavity_or_non_tree_topology'],branches:[],diagnostics:{}},
  candidates:[],candidate_status:'unavailable_mask_semantics_unverified',
  measurements:{reference_lumen_area_mm2:null,minimum_lumen_area_mm2:null,reference_lumen_diameter_mm:null,minimum_lumen_diameter_mm:null,estimated_percentage_narrowing:null,provisional_severity:null,availability:'unavailable_lumen_semantics_unverified'},
  clinical_validation:false,clinical_gate_authorized:false,training_release_authorized:false};

test('real-volume contract only accepts non-persistent, unavailable-lumen responses',()=>{
  assert.equal(validateRealVolumeResearch(realVolumeResult),realVolumeResult);
  for(const mutate of [
    v=>{v.clinical_gate_authorized=true;},
    v=>{v.training_release_authorized=true;},
    v=>{v.provenance.synthetic_model_used=true;},
    v=>{v.provenance.persisted=true;},
    v=>{v.candidates=[{center_ijk:[1,2,3]}];},
    v=>{v.measurements.estimated_percentage_narrowing=0;},
    v=>{v.provenance.ct_sha256='invalid';},
  ]) {const changed=structuredClone(realVolumeResult);mutate(changed);assert.throws(()=>validateRealVolumeResearch(changed));}
});

test('real-volume API sends a separate multipart pair and validates response',async()=>{
  let request;
  const ct=new Blob(['ct']);ct.name='source.nii';
  const mask=new Blob(['mask']);mask.name='vessel.nii.gz';
  const client={post:async(path,body,config)=>{request={path,body,config};return {status:200,data:realVolumeResult};}};
  const result=await analyzeRealVolumeResearch({ctVolume:ct,vesselMask:mask,signal:'abort-signal'},client);
  assert.equal(result,realVolumeResult);
  assert.equal(request.path,'/experimental-stenosis/real-volume/analyze');
  assert.equal(request.body.get('ct_volume').name,'source.nii');
  assert.equal(request.body.get('vessel_mask').name,'vessel.nii.gz');
  assert.equal(request.config.signal,'abort-signal');
  assert.equal(request.config.headers['Content-Type'],undefined);
});

test('public research sample and analysis responses reject target ground truth at every depth',()=>{
  for(const [base,mutate] of [
    [sample,v=>{v.class_label='moderate';}],
    [sample,v=>{v.provenance.synthetic_geometry_ground_truth={lesions:[]};}],
    [analysis,v=>{v.provenance.synthetic_class_label='moderate';}],
    [analysis,v=>{v.geometry_analysis.metrics.ground_truth_label='moderate';}],
  ]) { const value=structuredClone(base);mutate(value);assert.throws(()=>base===sample?validateSyntheticSample(value):validateSyntheticAnalysis(value)); }
});

for(const [label,mutate] of [
  ['patient association',v=>{v.provenance.patient_case_id=7;}],
  ['clinical gate',v=>{v.clinical_gate_authorized=true;}],
  ['measurement source hash',v=>{v.geometry_analysis.measurement_provenance.input_volume_sha256='b'.repeat(64);}],
  ['fabricated measurement confidence',v=>{v.geometry_analysis.metrics.measurement_confidence=.99;}],
  ['invalid severity boundaries',v=>{v.geometry_analysis.measurement_provenance.provisional_severity_thresholds_percent=[10,30,30,70];}],
  ['checkpoint identity',v=>{v.model.checkpoint_sha256='bad';}],
  ['uncalibrated scores',v=>{v.model.class_probabilities_uncalibrated=[1,1,1,1,1];}],
  ['Grad-CAM size',v=>{v.explainability.heatmap_values.pop();}],
]) test(`analysis rejects forged ${label}`,()=>{const value=structuredClone(analysis);mutate(value);assert.throws(()=>validateSyntheticAnalysis(value));});

test('synthetic API uses isolated endpoints and validates response before returning',async()=>{
  const calls=[],client={get:async(...args)=>{calls.push(['GET',...args]);return{status:200,data:{available:false,reason:'checkpoint not configured',scope:'synthetic_generated_phantoms_only',clinical_gate_authorized:false,training_release_authorized:false}};},post:async(...args)=>{calls.push(['POST',...args]);return{status:200,data:args[0].endsWith('/samples')?sample:analysis};}};
  const api=createExperimentalStenosisApi(client),request={sample_id:1,synthetic_class_id:2,seed:17};
  assert.equal((await api.status()).available,false);assert.equal((await api.sample(request)).sample_id,1);assert.equal((await api.analyze(request)).status,'completed_synthetic_research_only');
  assert.deepEqual(calls.map(call=>call.slice(0,2)),[['GET','/experimental-stenosis/status'],['POST','/experimental-stenosis/samples'],['POST','/experimental-stenosis/analyze']]);
  client.post=async()=>({status:200,data:{...sample,clinical_gate_authorized:true}});
  await assert.rejects(()=>api.sample(request));
});
