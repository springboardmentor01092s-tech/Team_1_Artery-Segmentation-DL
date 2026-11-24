// Local research preview only: never adapt this into AnalysisResult or a gate.
import * as nifti from 'nifti-reader-js';
import { geometryFingerprint, isHash, isUUID, validateGeometry } from './stenosis-results.js';
import { sameAffine } from './volume-geometry.js';
import { projectLesionMarkers } from './lesion-viewer.js';

export const EXPERIMENT_NOTICE = 'EXPERIMENTAL — NOT A DIAGNOSIS';
export const MAX_PREVIEW_BYTES = 2 * 1024 * 1024;
const fail = message => { throw new Error(message || 'Experimental preview could not be verified; no markers displayed.'); };
const hash = async bytes => Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)), n => n.toString(16).padStart(2, '0')).join('');
const keys = (object, expected) => object && typeof object === 'object' && !Array.isArray(object)
  && Object.keys(object).length === expected.length && expected.every(key => Object.hasOwn(object, key));
const finite = n => typeof n === 'number' && Number.isFinite(n);
const close = (a, b) => finite(a) && finite(b) && Math.abs(a - b) <= 1e-5 + Math.abs(b) * 1e-6;
const median = values => {
  const sorted = [...values].sort((a, b) => a - b), middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
};
const samePoint = (a, b) => a.every((n, i) => close(n, b[i]));

function checkCoordinates(ijk, world, geometry) {
  if (!Array.isArray(ijk) || ijk.length !== 3 || ijk.some((n, i) => !finite(n) || n < -1e-7 || n > geometry.shape[i] - 1 + 1e-7)
    || !Array.isArray(world) || world.length !== 3 || world.some(n => !finite(n))) fail('Invalid experimental section coordinates.');
  const expected = geometry.affine.slice(0, 3).map(row => row[3] + row.slice(0, 3).reduce((sum, n, i) => sum + n * ijk[i], 0));
  if (!samePoint(expected, world)) fail('Experimental IJK/RAS coordinates disagree.');
}

function inMask(ijk, geometry, mask) {
  const [i, j, k] = ijk.map(n => Math.floor(n + .5));
  return mask.labels[i + geometry.shape[0] * (j + geometry.shape[1] * k)] === 1;
}

function checkParameters(parameters) {
  const names = ['plane_pitch_mm','plane_radius_mm','sample_step_mm','reference_inner_mm','reference_outer_mm',
    'minimum_reference_samples_each_side','area_ratio_trigger','minimum_candidate_sections','junction_exclusion_mm'];
  if (!keys(parameters, names) || Object.values(parameters).some(n => !finite(n) || n <= 0)
    || parameters.area_ratio_trigger >= 1 || parameters.reference_inner_mm >= parameters.reference_outer_mm
    || ['minimum_reference_samples_each_side','minimum_candidate_sections'].some(key => !Number.isSafeInteger(parameters[key]) || parameters[key] < 2)) fail('Invalid experimental research parameters.');
  const radius = Math.ceil(parameters.plane_radius_mm / parameters.plane_pitch_mm);
  const pixelArea = parameters.plane_pitch_mm ** 2;
  if (!Number.isSafeInteger(radius) || radius < 1 || radius > 128 || !finite(pixelArea) || pixelArea <= 0) fail('Invalid experimental plane resource bounds.');
  return { pixelArea, planeNodes: (2 * radius + 1) ** 2 };
}

function checkBranch(branch, geometry, mask, parameters, plane) {
  if (!keys(branch, ['branch_id','sections','evaluable_sections','abstained_sections'])
    || typeof branch.branch_id !== 'string' || !/^[A-Za-z0-9_-]{1,64}$/.test(branch.branch_id)
    || !Array.isArray(branch.sections) || branch.sections.length < 2 || branch.sections.length > 512
    || !Number.isSafeInteger(branch.evaluable_sections) || branch.evaluable_sections < 0
    || !Number.isSafeInteger(branch.abstained_sections) || branch.abstained_sections < 0) fail('Incomplete experimental branch evidence.');
  const rows = branch.sections;
  const geometricReasons = new Set(['endpoint_exclusion','junction_exclusion','source_volume_boundary','background_center',
    'plane_fov_limited','ambiguous_disconnected_plane','internal_pocket']);
  for (const [i, row] of rows.entries()) {
    if (!keys(row, ['s_mm','sample_ijk','world_ras_mm','pixel_count','diagnostic_area_mm2','plane_components','status','reason','reference_samples_each_side'])
      || !finite(row.s_mm) || row.s_mm < 0 || !close(row.s_mm, i * parameters.sample_step_mm)
      || (i > 0 && row.s_mm <= rows[i - 1].s_mm)
      || !['abstained','evaluable_candidate_only'].includes(row.status)
      || !Array.isArray(row.reference_samples_each_side) || row.reference_samples_each_side.length !== 2
      || row.reference_samples_each_side.some(n => !Number.isSafeInteger(n) || n < 0 || n > rows.length)
      || (row.plane_components !== null && (!Number.isSafeInteger(row.plane_components) || row.plane_components < 0 || row.plane_components > plane.planeNodes))) fail('Malformed experimental section evidence.');
    checkCoordinates(row.sample_ijk, row.world_ras_mm, geometry);
    if (i > 0 && Math.hypot(...row.world_ras_mm.map((n, axis) => n - rows[i - 1].world_ras_mm[axis])) > parameters.sample_step_mm + 1e-5) fail('Experimental section order disagrees with physical arc length.');
    if (row.pixel_count === null) {
      if (row.diagnostic_area_mm2 !== null || row.status !== 'abstained' || !geometricReasons.has(row.reason)
        || row.reference_samples_each_side.some(n => n !== 0)) fail('Missing experimental plane evidence.');
      if (['endpoint_exclusion','junction_exclusion'].includes(row.reason) ? row.plane_components !== null : row.plane_components === null) fail();
      if (row.reason === 'ambiguous_disconnected_plane' && row.plane_components < 2) fail();
      if (row.reason === 'internal_pocket' && row.plane_components !== 1) fail();
    } else {
      const expectedArea = row.pixel_count * plane.pixelArea;
      if (!Number.isSafeInteger(row.pixel_count) || row.pixel_count < 1 || row.pixel_count > plane.planeNodes
        || !finite(row.diagnostic_area_mm2) || row.diagnostic_area_mm2 <= 0
        || Math.abs(row.diagnostic_area_mm2 - expectedArea) > 1e-12 + Math.abs(expectedArea) * 1e-9
        || row.plane_components !== 1 || !inMask(row.sample_ijk, geometry, mask)) fail('Invalid experimental pixel/area evidence.');
    }
  }
  const flags = [];
  for (const [i, row] of rows.entries()) {
    if (row.pixel_count === null) continue;
    const left = [], right = [];
    for (const other of rows) {
      const offset = other.s_mm - row.s_mm;
      if (offset <= -parameters.reference_inner_mm && offset >= -parameters.reference_outer_mm) left.push(other);
      if (offset >= parameters.reference_inner_mm && offset <= parameters.reference_outer_mm) right.push(other);
    }
    const sides = [left, right];
    const counts = sides.map(side => side.filter(r => r.diagnostic_area_mm2 !== null).length);
    if (counts.some((n, side) => n !== row.reference_samples_each_side[side])) fail('Experimental reference counts disagree with section records.');
    const supported = sides.every(side => side.length >= parameters.minimum_reference_samples_each_side && side.every(r => r.diagnostic_area_mm2 !== null));
    if (!supported) {
      if (row.status !== 'abstained' || row.reason !== 'insufficient_bidirectional_reference') fail('Unsupported experimental section cannot be evaluable.');
      continue;
    }
    if (row.status !== 'evaluable_candidate_only' || row.reason !== null) fail('Contradictory experimental section status.');
    const positions = sides.map(side => median(side.map(r => r.s_mm)));
    const areas = sides.map(side => median(side.map(r => r.diagnostic_area_mm2)));
    const reference = ((areas[1] - areas[0]) / (positions[1] - positions[0])) * (row.s_mm - positions[0]) + areas[0];
    if (!finite(reference) || reference <= 0) fail('Invalid experimental reference profile.');
    // Mirror the declared operator on supplied evidence, without a tolerance
    // that could lower its trigger. This does not authenticate execution/data.
    if (row.diagnostic_area_mm2 <= reference * parameters.area_ratio_trigger) flags.push(i);
  }
  const evaluable = rows.filter(row => row.status === 'evaluable_candidate_only').length;
  if (branch.evaluable_sections !== evaluable || branch.abstained_sections !== rows.length - evaluable) fail('Contradictory experimental branch counts.');
  const groups = [];
  for (const index of flags) {
    const last = groups.at(-1);
    if (last && last.at(-1) === index - 1) last.push(index); else groups.push([index]);
  }
  return groups.filter(group => group.length >= parameters.minimum_candidate_sections).map(group => ({
    branchId: branch.branch_id, rows: group.map(i => rows[i]),
  }));
}

export async function experimentalMaskIdentity(buffer, shape, targetLabel = 1) {
  if (!(buffer instanceof ArrayBuffer) || shape.length !== 3 || shape.some(n => !Number.isSafeInteger(n) || n < 2)
      || shape.reduce((a, b) => a * b, 1) > 4_000_000 || targetLabel !== 1) fail('Experimental preview mask resource/label limit.');
  const header = nifti.readHeader(buffer);
  if (header.datatypeCode !== 2 || shape.some((n, i) => header.dims[i + 1] !== n)) fail('Preview requires the displayed binary uint8 mask.');
  const labels = new Uint8Array(nifti.readImage(header, buffer));
  const prefix = new TextEncoder().encode('vascuai-experimental-mask-v1\0');
  const bytes = new Uint8Array(prefix.length + 16 + labels.length * 4), view = new DataView(bytes.buffer);
  bytes.set(prefix); let at = prefix.length;
  for (const n of [...shape, targetLabel]) { view.setUint32(at, n, true); at += 4; }
  // NIfTI uses i-fastest storage; Python's canonical array identity is C-order.
  for (let i = 0; i < shape[0]; i++) for (let j = 0; j < shape[1]; j++) for (let k = 0; k < shape[2]; k++) {
    const value = labels[i + shape[0] * (j + shape[1] * k)];
    if (value !== 0 && value !== 1) fail('Preview mask is not categorical binary data.');
    view.setUint32(at, value, true); at += 4;
  }
  return { sha256: await hash(bytes), labels };
}

export async function validateExperimentalPreview(data, geometry, segmentation, mask) {
  data = structuredClone(data);
  if (!keys(data, ['schema_version','algorithm','notice','measurement_status','source','geometry','parameters','parameter_status',
    'parameters_sha256','branch_geometry_sha256','candidates','branches','status','reason'])
    || data.schema_version !== 'experimental-candidates/1.0' || !keys(data.algorithm, ['id','version'])
    || data.algorithm.id !== 'experimental-mask-profile' || data.algorithm.version !== '0.1.0'
    || data.notice !== EXPERIMENT_NOTICE || data.measurement_status !== 'measurement_unavailable_no_validated_gate'
    || data.parameter_status !== 'unvalidated_research_parameters') fail();
  validateGeometry(data.geometry);
  if (data.geometry.shape.some((n, i) => n !== geometry.shape[i]) || !sameAffine(data.geometry.affine, geometry.affine)) fail('Experimental geometry differs from the displayed CT.');
  // Preserve the existing viewer's explicit oblique/shear abstention.
  const used = new Set();
  for (let c = 0; c < 3; c++) {
    const column = geometry.affine.slice(0, 3).map(row => row[c]);
    const axis = column.findIndex(n => Math.abs(n) > Math.hypot(...column) * .99999);
    if (axis < 0 || used.has(axis) || column.some((n, i) => i !== axis && Math.abs(n) > 1e-5)) fail('Oblique experimental preview is unavailable in this viewer.');
    used.add(axis);
  }
  const source = data.source;
  if (!keys(source, ['source_sha256','mask_sha256','geometry_fingerprint','mask_role','parent_segmentation_result_id','target_label'])
    || source.mask_role !== 'model_prediction' || source.target_label !== 1 || !isUUID(source.parent_segmentation_result_id)
    || source.parent_segmentation_result_id !== segmentation.id || source.source_sha256 !== segmentation.metadata.source_sha256
    || !isHash(source.source_sha256) || source.mask_sha256 !== mask.sha256
    || source.geometry_fingerprint !== await geometryFingerprint({...data.geometry, shape:geometry.shape, affine:geometry.affine}, source.source_sha256)) fail('Preview source/mask identity mismatch; annotations are not predictions.');
  const plane = checkParameters(data.parameters);
  if (!isHash(data.parameters_sha256) || !isHash(data.branch_geometry_sha256)
    || !(mask.labels instanceof Uint8Array) || mask.labels.length !== geometry.shape.reduce((a, b) => a * b, 1)
    || !Array.isArray(data.candidates) || data.candidates.length > 128 || !Array.isArray(data.branches) || data.branches.length > 8) fail();
  // Parameters are displayed as supplied research provenance, not authenticated
  // evidence of execution. Mask/source hashes bind bytes, not algorithm accuracy.
  const branchIds = new Set(), groups = []; let sectionCount = 0, evaluable = 0;
  for (const branch of data.branches) {
    const expected = checkBranch(branch, geometry, mask, data.parameters, plane);
    if (branchIds.has(branch.branch_id)) fail('Duplicate experimental branch.');
    branchIds.add(branch.branch_id); sectionCount += branch.sections.length;
    evaluable += branch.evaluable_sections; groups.push(...expected);
  }
  if (sectionCount > 2048 || sectionCount * plane.planeNodes > 8_000_000) fail('Experimental preview section resource limit.');
  if (data.candidates.length !== groups.length) fail('Experimental candidates lack matching section evidence.');
  const ids = new Set(), matched = new Set();
  for (const candidate of data.candidates) {
    if (!keys(candidate, ['candidate_id','kind','branch_id','sample_ijk','world_ras_mm','interval_s_mm','supporting_sections'])
      || candidate.kind !== 'experimental_candidate' || !/^candidate-\d{3}$/.test(candidate.candidate_id) || ids.has(candidate.candidate_id)
      || !branchIds.has(candidate.branch_id)
      || !Array.isArray(candidate.sample_ijk) || candidate.sample_ijk.length !== 3
      || candidate.sample_ijk.some((n, i) => !finite(n) || n < -1e-7 || n > geometry.shape[i] - 1 + 1e-7)
      || !Array.isArray(candidate.world_ras_mm) || candidate.world_ras_mm.length !== 3
      || !Array.isArray(candidate.interval_s_mm) || candidate.interval_s_mm.length !== 2 || candidate.interval_s_mm.some(n => !finite(n) || n < 0)
      || candidate.interval_s_mm[0] >= candidate.interval_s_mm[1] || !Number.isSafeInteger(candidate.supporting_sections)
      || candidate.supporting_sections < data.parameters.minimum_candidate_sections) fail();
    ids.add(candidate.candidate_id);
    checkCoordinates(candidate.sample_ijk, candidate.world_ras_mm, geometry);
    const index = groups.findIndex(group => group.branchId === candidate.branch_id
      && close(group.rows[0].s_mm, candidate.interval_s_mm[0]) && close(group.rows.at(-1).s_mm, candidate.interval_s_mm[1]));
    if (index < 0 || matched.has(index) || groups[index].rows.length !== candidate.supporting_sections) fail('Experimental interval/support count disagrees with contiguous evidence.');
    matched.add(index);
    const center = groups[index].rows.reduce((best, row) => row.diagnostic_area_mm2 < best.diagnostic_area_mm2 ? row : best);
    if (!samePoint(candidate.sample_ijk, center.sample_ijk) || !samePoint(candidate.world_ras_mm, center.world_ras_mm)
      || !inMask(candidate.sample_ijk, geometry, mask)) fail('Experimental center is not supported by its section evidence.');
  }
  const expectedStatus = groups.length ? 'candidate_preview' : evaluable ? 'no_candidates_in_evaluable_sections' : 'abstained';
  if (data.status !== expectedStatus || (evaluable ? data.reason !== null : data.branches.length
    ? data.reason !== 'no_evaluable_reference_support' : !['empty_mask','disconnected_source_mask'].includes(data.reason))) fail('Contradictory experimental preview status.');
  if (!data.branches.length) {
    const emptyTarget = !mask.labels.some(n => n === 1);
    if ((data.reason === 'empty_mask') !== emptyTarget) fail('Experimental source abstention contradicts the target mask.');
  }
  // No caller mutation or retained mutable input is used by the marker layer.
  return structuredClone(data);
}

export function projectExperimentalCandidates(viewer, preview, selectedId) {
  return projectLesionMarkers(viewer, preview.candidates.map(candidate => ({
    lesion_id: candidate.candidate_id, location: { world_coordinates: candidate.world_ras_mm },
  })), selectedId);
}

export function navigateExperimentalCandidate(viewer, candidate) {
  const fraction = viewer.mm2frac(candidate.world_ras_mm, 0, true);
  if (Array.from(fraction).some(n => !finite(n) || n < 0 || n > 1)) fail('Experimental marker is outside this CT.');
  viewer.scene.crosshairPos = fraction; viewer.drawScene(); viewer.onLocationChange();
}
