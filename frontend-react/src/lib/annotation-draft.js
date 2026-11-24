// Local, unverified reader preparation. Never a clinical report or training label.
export const ANNOTATION_DRAFT_VERSION = 'lesion-annotation-workspace/0.1';
export const MAX_ANNOTATION_DRAFT_BYTES = 2 * 1024 * 1024;
export const POINT_FIELDS = Object.freeze(['center_ijk', 'proximal_boundary_ijk', 'distal_boundary_ijk',
  'minimum_caliper_start_ijk', 'minimum_caliper_end_ijk', 'reference_caliper_start_ijk', 'reference_caliper_end_ijk']);
export const SEVERITY_CHOICES = Object.freeze(['minimal', 'mild', 'moderate', 'severe', 'occluded', 'ungradable']);
const HASH = /^[a-f0-9]{64}$/;
const UUID = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i;
const fail = () => { throw new Error('Invalid or mismatched annotation draft. No clinical result was imported.'); };
const exact = (value, keys) => value && typeof value === 'object' && !Array.isArray(value)
  && Object.keys(value).length === keys.length && keys.every(key => Object.hasOwn(value, key));
const vector = (value, length, predicate) => Array.isArray(value) && value.length === length && Array.from(value).every(predicate);
const finitePoint = value => vector(value, 3, Number.isFinite);
const text = (value, max = 1000) => typeof value === 'string' && value.length <= max;

// Geometry-only entry point for CT-only readers; no invented segmentation ID.
export function validateNativeGeometry(source) {
  if(source?.units!=='mm'||!vector(source.shape,3,n=>Number.isSafeInteger(n)&&n>0)
    ||!Number.isSafeInteger(source.shape.reduce((a,b)=>a*b,1))
    ||!vector(source.affine,4,row=>vector(row,4,Number.isFinite))||source.affine[3].some((v,i)=>v!==(i===3?1:0)))fail();
  const [[u,v,w],[p,q,r],[s,t,k]]=source.affine;
  const determinant=u*(q*k-r*t)-v*(p*k-r*s)+w*(p*t-q*s),scale=Math.hypot(u,p,s)*Math.hypot(v,q,t)*Math.hypot(w,r,k);
  if(!Number.isFinite(determinant)||!Number.isFinite(scale)||!(scale>0)||Math.abs(determinant)/scale<1e-8)fail();
  return determinant;
}

// One source/geometry validator for capture, restore and both export snapshots.
// The optional expected source prevents coordinates from crossing CT frames.
export function validateAnnotationSource(source, expectedSource = source) {
  if (!exact(source,['case_id','source_sha256','segmentation_result_id','shape','affine','units'])
      || !Number.isSafeInteger(source.case_id) || source.case_id<=0
      || typeof source.source_sha256!=='string' || !HASH.test(source.source_sha256)
      || typeof source.segmentation_result_id!=='string' || !UUID.test(source.segmentation_result_id) || source.units!=='mm'
      || !vector(source.shape,3,n=>Number.isSafeInteger(n)&&n>0)
      || !Number.isSafeInteger(source.shape.reduce((a,b)=>a*b,1))
      || !vector(source.affine,4,row=>vector(row,4,Number.isFinite))
      || source.affine[3].some((v,i)=>v!==(i===3?1:0))) fail();
  const determinant = validateNativeGeometry(source);
  if (expectedSource !== source) {
    validateAnnotationSource(expectedSource);
    if (Object.keys(source).some(key=>JSON.stringify(source[key])!==JSON.stringify(expectedSource[key]))) fail();
  }
  return determinant;
}

export function annotationSource(caseId, result, geometry) {
  const source = { case_id: Number(caseId), source_sha256: result?.metadata?.source_sha256,
    segmentation_result_id: result?.id, shape: geometry?.shape, affine: geometry?.affine, units: geometry?.units };
  if (result?.case_id !== source.case_id) fail();
  validateAnnotationSource(source);
  return JSON.parse(JSON.stringify(source));
}

export function worldToNativeIjk(world, source, expectedSource = source) {
  validateAnnotationSource(source, expectedSource);
  return worldToNativeGeometry(world,source);
}

export function worldToNativeGeometry(world,source) {
  const det = validateNativeGeometry(source);
  if (!finitePoint(world)) fail();
  const a = source.affine;
  const [x, y, z] = world.map((v, i) => v - a[i][3]);
  const [[u,v,w], [p,q,r], [s,t,k]] = a;
  const point = [((q*k-r*t)*x+(w*t-v*k)*y+(v*r-w*q)*z)/det,
    ((r*s-p*k)*x+(u*k-w*s)*y+(w*p-u*r)*z)/det,
    ((p*t-q*s)*x+(v*s-u*t)*y+(u*q-v*p)*z)/det];
  if (!finitePoint(point) || point.some((n,i) => n < -1e-5 || n > source.shape[i]-1+1e-5)) {
    throw new Error('Crosshair is outside the original CT grid. Select a voxel inside the CT.');
  }
  return point.map((n,i) => Number(Math.min(source.shape[i]-1,Math.max(0,n)).toFixed(5)));
}

export function newDraftLesion() {
  return { draft_id: crypto.randomUUID(), artery: '', segment: '', segment_convention: '',
    ...Object.fromEntries(POINT_FIELDS.map(key => [key,null])), minimum_lumen_diameter_mm: null,
    adjacent_reference_diameter_mm: null, reference_selection: '', percentage_narrowing: null,
    percentage_basis: '', severity_category: null, unavailable_reason: 'Not recorded; no clinical measurement inferred.', notes: '' };
}

export function newAnnotationDraft(source) {
  validateAnnotationSource(source);
  return { schema_version: ANNOTATION_DRAFT_VERSION, source: JSON.parse(JSON.stringify(source)),
    status: 'unverified_local_draft', label_origin: 'manual_reader_preparation_not_expert_ground_truth',
    algorithm_exposure: 'predicted_segmentation_available_in_workspace', reader_independence_verified: false,
    clinical_validation: false, training_eligible: false, quantitative_gate_authorized: false,
    clinical_gate_authorized: false, training_release_authorized: false,
    reviewer_reference: '', protocol_reference: '', proposed_lesions: [] };
}

export function validateAnnotationDraft(value, source) {
  validateAnnotationSource(source);
  const rootKeys = ['schema_version','source','status','label_origin','algorithm_exposure','reader_independence_verified',
    'clinical_validation','training_eligible','quantitative_gate_authorized','clinical_gate_authorized','training_release_authorized',
    'reviewer_reference','protocol_reference','proposed_lesions'];
  if (!exact(value, rootKeys) || value.schema_version !== ANNOTATION_DRAFT_VERSION
      || value.status !== 'unverified_local_draft' || value.label_origin !== 'manual_reader_preparation_not_expert_ground_truth'
      || value.algorithm_exposure !== 'predicted_segmentation_available_in_workspace'
      || ['reader_independence_verified','clinical_validation','training_eligible','quantitative_gate_authorized',
        'clinical_gate_authorized','training_release_authorized'].some(key => value[key] !== false)
      || !text(value.reviewer_reference,200) || !text(value.protocol_reference,500)
      || !Array.isArray(value.proposed_lesions) || value.proposed_lesions.length > 100) fail();
  validateAnnotationSource(value.source, source);
  const keys = ['draft_id','artery','segment','segment_convention',...POINT_FIELDS,'minimum_lumen_diameter_mm',
    'adjacent_reference_diameter_mm','reference_selection','percentage_narrowing','percentage_basis','severity_category','unavailable_reason','notes'];
  const ids = new Set();
  for (const lesion of value.proposed_lesions) {
    if (!exact(lesion, keys) || !UUID.test(lesion.draft_id) || ids.has(lesion.draft_id)
        || !['','LM','LAD','LCx','RCA','graft','other'].includes(lesion.artery)
        || !text(lesion.segment,200) || !text(lesion.segment_convention,200)
        || !text(lesion.reference_selection,500) || !text(lesion.percentage_basis,500)
        || !text(lesion.notes) || !text(lesion.unavailable_reason) || !lesion.unavailable_reason.trim()
        || (lesion.severity_category !== null && !SEVERITY_CHOICES.includes(lesion.severity_category))) fail();
    ids.add(lesion.draft_id);
    for (const key of POINT_FIELDS) if (lesion[key] !== null && (!finitePoint(lesion[key])
        || lesion[key].some((n,i) => n < 0 || n > source.shape[i]-1))) fail();
    for (const key of ['minimum_lumen_diameter_mm','adjacent_reference_diameter_mm','percentage_narrowing']) {
      const n = lesion[key];
      if (n !== null && (typeof n !== 'number' || !Number.isFinite(n) || n < 0
          || (key === 'adjacent_reference_diameter_mm' && n === 0) || (key === 'percentage_narrowing' && n > 100))) fail();
    }
    if (lesion.percentage_narrowing !== null && !lesion.percentage_basis.trim()) fail();
    if (lesion.adjacent_reference_diameter_mm !== null && !lesion.reference_selection.trim()) fail();
  }
  return value;
}

export function annotationDraftBlob(value, source) {
  validateAnnotationDraft(value, source);
  const content = JSON.stringify(value, null, 2);
  if (new TextEncoder().encode(content).byteLength > MAX_ANNOTATION_DRAFT_BYTES) fail();
  // Validate the detached snapshot before allocating any downloadable Blob.
  validateAnnotationDraft(JSON.parse(content), source);
  return new Blob([content], { type: 'application/json;charset=utf-8' });
}
