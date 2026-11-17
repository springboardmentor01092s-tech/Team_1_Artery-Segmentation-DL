// Node test helper only. Bundles are real serialized outputs of the synthetic
// Python extractor, independently re-extracted by backend regression tests.
import { readFileSync } from 'node:fs';
import { gunzipSync } from 'node:zlib';
import { experimentalMaskIdentity } from '../src/lib/experimental-candidates.js';

export async function loadExperimentalFixture(layout = 'flipped', variant = 'preview') {
  if (!['flipped','permuted'].includes(layout) || !['preview','no_candidate_preview','abstained_preview'].includes(variant)) throw new Error('Unknown synthetic fixture');
  const bundle = JSON.parse(readFileSync(new URL(`./fixtures/experimental-preview-${layout}.json`, import.meta.url), 'utf8'));
  const ctGzip = Buffer.from(bundle.ct_gzip_base64, 'base64'), maskGzip = Buffer.from(bundle.mask_gzip_base64, 'base64');
  const raw = gunzipSync(maskGzip), maskBuffer = raw.buffer.slice(raw.byteOffset, raw.byteOffset + raw.byteLength);
  const preview = structuredClone(bundle[variant]), geometry = structuredClone(bundle.preview.geometry);
  const segmentation = {id:preview.source.parent_segmentation_result_id, case_id:1, stale:false,
    metadata:{shape:geometry.shape, affine:geometry.affine, xyzt_units:2, source_sha256:preview.source.source_sha256}};
  return {preview, geometry, segmentation, maskBuffer, verifiedMask:await experimentalMaskIdentity(maskBuffer, geometry.shape), ctGzip, maskGzip};
}
