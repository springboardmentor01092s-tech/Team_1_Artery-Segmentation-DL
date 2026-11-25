// Local research only. No human identities, server submissions or training labels.
import { validateExperimentalPreview } from './experimental-candidates.js';
import { validateNativeGeometry } from './annotation-draft.js';
import { isHash } from './stenosis-results.js';
import {checkedOfflineReceipt} from '../api/offline-research-contract.js';

export const RESEARCH_VERSION = 'simulated-research-assessment/0.1';
export const RESEARCH_NOTICE = 'Algorithm-assisted provisional research — not expert review or a diagnosis';
const fail = message => { throw new Error(message); };
export const canonicalResearchJson = value => JSON.stringify(sort(value));
function sort(value) {
  if (Array.isArray(value)) return value.map(sort);
  if (value && typeof value === 'object') return Object.fromEntries(Object.keys(value).sort().map(key => [key, sort(value[key])]));
  return value;
}
async function digest(value) {
  const bytes = new TextEncoder().encode(canonicalResearchJson(value));
  return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)), n => n.toString(16).padStart(2, '0')).join('');
}
function freeze(value) {
  if (value && typeof value === 'object') { Object.values(value).forEach(freeze); Object.freeze(value); }
  return value;
}
const median = values => { const a = [...values].sort((x,y) => x-y), n = a.length; return n % 2 ? a[(n-1)/2] : (a[n/2-1]+a[n/2])/2; };
const mean = values => values.reduce((a,b) => a+b,0)/values.length;
const diameter = area => 2*Math.sqrt(area/Math.PI);

// Neither procedure sees the other's output. Both share the same mask, sampling,
// availability decisions and unvalidated trigger: they are NOT independent experts.
function assess(profile, role) {
  const p = profile.parameters;
  return profile.branches.map(branch => {
    const rows = branch.sections.map(row => {
      if (row.status !== 'evaluable_candidate_only') return { s_mm:row.s_mm, status:'unassessable', reason:row.reason,
        reference_area_mm2:null, diagnostic_area_ratio:null, proposed:false };
      const sides = [-1,1].map(sign => branch.sections.filter(other => {
        const distance = (other.s_mm-row.s_mm)*sign;
        return distance >= p.reference_inner_mm && distance <= p.reference_outer_mm;
      }));
      if (sides.some(side => side.length < p.minimum_reference_samples_each_side || side.some(r => !(r.diagnostic_area_mm2 > 0)))) {
        fail('Reference evidence is incomplete.');
      }
      const reference = role === 'R1'
        ? (() => { const positions = sides.map(side => median(side.map(r => r.s_mm)));
          const areas = sides.map(side => median(side.map(r => r.diagnostic_area_mm2)));
          return ((areas[1]-areas[0])/(positions[1]-positions[0]))*(row.s_mm-positions[0])+areas[0]; })()
        : Math.min(...sides.map(side => mean(side.map(r => r.diagnostic_area_mm2))));
      if (!(reference > 0) || !Number.isFinite(reference)) fail('Invalid reference area.');
      return {s_mm:row.s_mm, status:'research_evaluable', reason:null, reference_area_mm2:reference,
        diagnostic_area_ratio:row.diagnostic_area_mm2/reference,
        proposed:row.diagnostic_area_mm2 <= reference*p.area_ratio_trigger};
    });
    const groups = [];
    rows.forEach((row,index) => {
      if (!row.proposed) return;
      const group = groups.at(-1);
      if (group && group.at(-1) === index-1) group.push(index); else groups.push([index]);
    });
    const proposals = groups.filter(group => group.length >= p.minimum_candidate_sections).map((group,index) => {
      const center = group.reduce((best,i) => branch.sections[i].diagnostic_area_mm2 < branch.sections[best].diagnostic_area_mm2 ? i : best);
      const source = branch.sections[center], reference = rows[center].reference_area_mm2;
      return {proposal_id:`${role}-${branch.branch_id}-${index+1}`, status:'algorithmically_proposed_unverified',
        artery:null, artery_unavailable_reason:'No anatomical artery identification model or qualified reading.',
        branch_id:branch.branch_id, center_ijk:source.sample_ijk, world_ras_mm:source.world_ras_mm,
        proximal_ijk:branch.sections[group[0]].sample_ijk, distal_ijk:branch.sections[group.at(-1)].sample_ijk,
        boundary_definition:'First/last triggering sample in supplied branch order; not anatomical proximal/distal truth.',
        interval_s_mm:[rows[group[0]].s_mm, rows[group.at(-1)].s_mm], supporting_sections:group.length,
        research_measurement:{method:'area_equivalent_diameter_from_categorical_plane/0.1',
          minimum_area_equivalent_diameter_mm:diameter(source.diagnostic_area_mm2),
          reference_area_equivalent_diameter_mm:diameter(reference),
          diagnostic_diameter_reduction_percent:100*(1-Math.sqrt(source.diagnostic_area_mm2/reference)),
          uncertainty:null, uncertainty_status:'not_estimated', severity_category:null,
          limitation:'Unvalidated profile/reference selection; not a clinical caliper measurement or stenosis percentage.'},
        confidence:null, confidence_status:'unavailable_no_calibrated_stenosis_model'};
    });
    return {branch_id:branch.branch_id, sections:rows, proposals,
      evaluable_sections:rows.filter(row => row.status === 'research_evaluable').length,
      unassessable_sections:rows.filter(row => row.status === 'unassessable').length};
  });
}

function compare(r1,r2) {
  return r1.map((branch,b) => ({branch_id:branch.branch_id,
    sections:branch.sections.map((row,i) => {
      const other = r2[b].sections[i];
      return {s_mm:row.s_mm, r1_proposed:row.proposed, r2_proposed:other.proposed,
        status:row.status === 'unassessable' || other.status === 'unassessable' ? 'unassessable'
          : row.proposed !== other.proposed ? 'disagreement_unresolved' : row.proposed ? 'concordant_proposal_unverified' : 'no_trigger_not_normal'};
    }),
    // Preserve all proposals: no voting, merging or automatic resolution.
    r1_proposal_ids:branch.proposals.map(row => row.proposal_id), r2_proposal_ids:r2[b].proposals.map(row => row.proposal_id)}));
}

function point(value, geometry) {
  if (!Array.isArray(value) || value.length !== 3 || value.some((n,i) => !Number.isFinite(n) || n < 0 || n > geometry.shape[i]-1)) fail('Caliper endpoints must be finite native IJK inside this CT.');
  return geometry.affine.slice(0,3).map(row => row[3]+row.slice(0,3).reduce((sum,n,i) => sum+n*value[i],0));
}
export function researchCalipers(input, geometry) {
  validateNativeGeometry({...geometry, units:geometry.units ?? geometry.world_unit});
  if(geometry.units!==undefined&&geometry.world_unit!==undefined&&geometry.units!==geometry.world_unit)fail('Conflicting spatial units.');
  const axes=[0,1,2].map(c=>geometry.affine.slice(0,3).map(row=>row[c]));
  for(let i=0;i<3;i++)for(let j=i+1;j<3;j++) {
    if(Math.abs(axes[i].reduce((sum,n,k)=>sum+n*axes[j][k],0))/(Math.hypot(...axes[i])*Math.hypot(...axes[j]))>1e-6)fail('Sheared research caliper geometry is unsupported.');
  }
  const keys = ['minimum_start_ijk','minimum_end_ijk','reference_start_ijk','reference_end_ijk','method_evidence'];
  if (!input || Object.keys(input).length !== keys.length || keys.some(key => !Object.hasOwn(input,key))
      || typeof input.method_evidence !== 'string' || input.method_evidence.length > 1000) fail('Invalid research caliper record.');
  const positions = keys.slice(0,4).map(key => input[key] === null ? null : point(input[key],geometry));
  const base = {origin:'manual_unverified_research', minimum_diameter_mm:null, reference_diameter_mm:null,
    diagnostic_diameter_reduction_percent:null, severity_category:null, uncertainty:null, uncertainty_status:'not_estimated',
    clinical_gate_authorized:false, training_release_authorized:false};
  if (positions.some(value => value === null)) return {...base,status:'unassessable',reason:'Incomplete endpoints; no zero or measurement inferred.'};
  if (!input.method_evidence.trim()) fail('Document the plane and reference-selection evidence.');
  const lengths = [[0,1],[2,3]].map(([a,b]) => Math.hypot(...positions[a].map((n,i) => n-positions[b][i])));
  if (lengths.some(n => !Number.isFinite(n) || n <= 0)) fail('Zero-length or invalid caliper.');
  if (lengths[0] > lengths[1]) return {...base,status:'unassessable',reason:'Minimum exceeds selected reference; no clamping or clinical interpretation.'};
  return {...base,status:'unverified_arithmetic_only',reason:'Endpoint/plane/reference appropriateness not clinically verified.',
    method:'100*(1-D_min/D_reference); affine Euclidean endpoint distances in mm',
    minimum_diameter_mm:lengths[0],reference_diameter_mm:lengths[1],diagnostic_diameter_reduction_percent:100*(1-lengths[0]/lengths[1])};
}

export const blankResearchCalipers = () => ({minimum_start_ijk:null,minimum_end_ijk:null,reference_start_ijk:null,reference_end_ijk:null,method_evidence:''});

function modelIdentity(segmentation) {
  // Echo only actual saved model metadata; a source hash cannot reconstruct it.
  const meta = segmentation.metadata;
  const hash = meta.checkpoint_sha256 ?? null;
  if (hash !== null && !isHash(hash)) fail('Invalid recorded model checkpoint.');
  const threshold = meta.threshold ?? null;
  if (threshold !== null && (typeof threshold !== 'number' || !Number.isFinite(threshold) || threshold < 0 || threshold > 1)) fail('Invalid saved inference threshold.');
  const architecture = meta.architecture ?? null;
  if (architecture !== null && (typeof architecture !== 'string' || architecture.length > 120)) fail('Invalid saved architecture.');
  const identity = Object.fromEntries(['model_name','model_version','recipe'].map(key=>{
    const value=meta[key]??null;
    if(value!==null && (typeof value!=='string'||value.length>120))fail('Invalid saved model identity.');
    return [key,value];
  }));
  return {architecture,...identity,checkpoint_sha256:hash,threshold,identity_status:hash && architecture && threshold !== null ? 'saved_metadata_not_execution_attestation' : 'incomplete_saved_model_metadata',
    assessment_model:null,assessment_model_reason:'Deterministic geometry procedures, not a trained stenosis model or LLM.'};
}

// This is the public trust boundary: every call revalidates against the currently
// displayed CT, actual categorical mask bytes and selected segmentation record.
export async function createResearchAssessment(preview, context, calipers = blankResearchCalipers()) {
  if (!(context?.mask?.labels instanceof Uint8Array) || context.mask.labels.length > 4_000_000
      || context.mask.labels.some(n => n !== 0 && n !== 1)) fail('A bounded binary mask is required.');
  const ctx = {geometry:structuredClone(context.geometry),segmentation:structuredClone(context.segmentation),
    mask:{sha256:context.mask.sha256,labels:new Uint8Array(context.mask.labels)}};
  const checked = await validateExperimentalPreview(preview,ctx.geometry,ctx.segmentation,ctx.mask);
  // Recompute the canonical C-order mask identity from NIfTI i-fastest labels.
  const prefix = new TextEncoder().encode('vascuai-experimental-mask-v1\0');
  const bytes = new Uint8Array(prefix.length+16+ctx.mask.labels.length*4), view = new DataView(bytes.buffer);
  bytes.set(prefix); let at = prefix.length;
  for (const n of [...checked.geometry.shape,1]) {view.setUint32(at,n,true);at+=4;}
  const [nx,ny,nz] = checked.geometry.shape;
  for (let i=0;i<nx;i++) for (let j=0;j<ny;j++) for (let k=0;k<nz;k++) {
    view.setUint32(at,ctx.mask.labels[i+nx*(j+ny*k)],true);at+=4;
  }
  const maskHash = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),n=>n.toString(16).padStart(2,'0')).join('');
  if (maskHash !== checked.source.mask_sha256) fail('Actual mask bytes do not match the research source.');
  if (!Number.isSafeInteger(ctx.segmentation.case_id) || ctx.segmentation.case_id < 1 || ctx.segmentation.stale !== false) fail('A current saved case/run is required.');
  return assembleResearchAssessment(checked,ctx.segmentation,calipers);
}

export async function createOfflineResearchAssessment(receipt,result){
  const checked=checkedOfflineReceipt(receipt,result);
  return assembleResearchAssessment(checked.profile,checked.segmentation,blankResearchCalipers());
}

async function assembleResearchAssessment(checked,segmentation,calipers){
  const input = structuredClone(calipers);
  const measurement = researchCalipers(input,checked.geometry);
  const source = {...checked.source,case_id:segmentation.case_id};
  const sourceEvidenceSha = await digest({source,geometry:checked.geometry,profile:checked});
  const common = {schema_version:'simulated-research-record/0.1', source_evidence_sha256:sourceEvidenceSha,
    origin:'algorithmic_simulation_on_model_derived_mask',clinical_gate_authorized:false,training_release_authorized:false,
    qualified_human_reviewer:false,reviewer_independence_verified:false,confidence:null};
  const records = [];
  for (const role of ['R1','R2']) {
    const record = {...common,role,procedure_version:'0.1',procedure:role === 'R1' ? 'bidirectional_median_interpolated_reference' : 'conservative_minimum_directional_mean_reference',
      evidence:assess(checked,role)};
    records.push(freeze({record,sha256:await digest(record)}));
  }
  const third = {...common,role:'R3',procedure_version:'0.1',procedure:'compare_frozen_assessments_without_consensus_label',
    parent_sha256:records.map(item => item.sha256),evidence:compare(records[0].record.evidence,records[1].record.evidence),
    adjudication_status:'provisional_comparison_not_clinical_adjudication'};
  records.push(freeze({record:third,sha256:await digest(third)}));
  const document = {schema_version:RESEARCH_VERSION,notice:RESEARCH_NOTICE,source,geometry:checked.geometry,
    profile:checked,model_provenance:modelIdentity(segmentation),input_evidence_sha256:sourceEvidenceSha,
    inference_configuration:{profile_algorithm:checked.algorithm,profile_parameters:checked.parameters,parameters_sha256:checked.parameters_sha256,
      branch_geometry_sha256:checked.branch_geometry_sha256,parameter_status:checked.parameter_status},
    independent_assessment_limitation:'Different procedures share one mask/profile and sampling errors. No human or statistical independence is established.',
    clinical_gate_authorized:false,training_release_authorized:false,records,manual_caliper_input:input,manual_caliper_result:measurement,
    attribution:{status:'unavailable_no_stenosis_model_prediction',method:null,map:null,
      reason:'Geometry trigger support is not Grad-CAM. Segmentation masks are not stenosis logits; no attribution was generated.'}};
  const result = {document,sha256:await digest(document)};
  if (new TextEncoder().encode(JSON.stringify(result)).byteLength > 2*1024*1024) fail('Research assessment exceeds the 2 MiB output limit.');
  return freeze(result);
}

export async function validateResearchAssessment(value, context) {
  // Do not trust supplied hashes, safety flags, records, model identity or arithmetic.
  // Recompute everything from current source evidence before restoring or exporting.
  const snapshot = JSON.parse(JSON.stringify(value));
  if (snapshot?.document?.schema_version !== RESEARCH_VERSION) fail('Unsupported standalone research document.');
  const expected = await createResearchAssessment(snapshot.document.profile,context,snapshot.document.manual_caliper_input);
  if (canonicalResearchJson(snapshot) !== canonicalResearchJson(expected)) fail('Research content/hash/source mismatch. No assessment accepted.');
  return expected;
}

export async function researchAssessmentBlob(value, context) {
  const checked = await validateResearchAssessment(value,context);
  return new Blob([JSON.stringify(checked,null,2)],{type:'application/json;charset=utf-8'});
}
