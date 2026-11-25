import { decode } from '../lib/nifti-decode.js';
export { decode } from '../lib/nifti-decode.js';
import { inspectVolume, validatePair, MAX_TRANSFER_BYTES } from '../lib/volume-geometry.js';
import { inspectAttribution, MAX_ATTRIBUTION_BYTES, MAX_ATTRIBUTION_EXPANDED } from '../lib/attribution.js';

function checkTransferSize(buffer) {
  if (buffer.byteLength > MAX_TRANSFER_BYTES) throw new Error('Volume input exceeds the browser transfer limit.');
}

if (typeof self !== 'undefined') self.onmessage = async ({ data: { ct, mask, region, attribution, explanation, artifact_sha256, metadata } }) => {
  try {
    if (attribution) {
      if(attribution.byteLength>MAX_ATTRIBUTION_BYTES) throw new Error('Attribution exceeds the browser transfer limit.');
      const hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',attribution)),v=>v.toString(16).padStart(2,'0')).join('');
      if(hash!==explanation.content_sha256) throw new Error('Attribution checksum does not match its provenance.');
      const expanded=decode(attribution,Math.min(MAX_ATTRIBUTION_EXPANDED,metadata.shape.reduce((a,b)=>a*b,1)*4+1024*1024));
      const geometry=inspectAttribution(expanded,explanation,metadata);
      self.postMessage({attribution:expanded,geometry},[expanded]);return;
    }
    if (region) {
      checkTransferSize(region);
      const digest = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', region)), v => v.toString(16).padStart(2, '0')).join('');
      if (digest !== artifact_sha256) throw new Error('Candidate-region checksum does not match its provenance.');
      const voxels = metadata.shape.reduce((a, b) => a * b, 1);
      const labels = decode(region, voxels + 1024 * 1024);
      const inspected = inspectVolume(labels, { mask: true });
      validatePair(inspected, inspected, metadata);
      self.postMessage({ region: labels, geometry: inspected }, [labels]);
      return;
    }
    checkTransferSize(ct);
    checkTransferSize(mask);
    if (!/^[a-f0-9]{64}$/.test(metadata.source_sha256)) throw new Error('The selected run has no verifiable source checksum.');
    const hash = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', ct)), v => v.toString(16).padStart(2, '0')).join('');
    if (hash !== metadata.source_sha256) throw new Error('The source changed during retrieval. Refresh history and reopen a current result.');
    self.postMessage({ phase: 'Decoding and validating NIfTI geometry…' });
    const voxels = metadata.shape.reduce((a, b) => a * b, 1);
    const source = decode(ct, Math.min(MAX_TRANSFER_BYTES, voxels * 8 + 1024 * 1024));
    const labels = decode(mask, voxels + 1024 * 1024);
    ct = null; mask = null;
    const ctGeometry = inspectVolume(source);
    const maskGeometry = inspectVolume(labels, { mask: true });
    const geometry = validatePair(ctGeometry, maskGeometry, metadata);
    self.postMessage({ ct: source, mask: labels, geometry }, [source, labels]);
  } catch (error) {
    self.postMessage({ error: error.message || 'Volume decoding failed.' });
  }
};
