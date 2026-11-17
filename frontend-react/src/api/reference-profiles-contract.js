// Separate, specifically approved reference display. Not the clinical registry.
export const REFERENCE_GATE = Object.freeze({
  id: 'reference-profile/0.1',
  methodSha256: 'aca8d3751a22cca9379df1d9edb3fded895b014263e94d639aee9d7ca32132a4',
  artifactSha256: '1330b37432778e1170faaec94bae7141b364b4cdfa2ec20367da93d3f156642a',
});
export const REFERENCE_NOTICE = 'reference-derived research measurement, not validated';

export async function validateReferenceBytes(bytes) {
  // Hash the detached received bytes, not a client-supplied digest/validated flag.
  const snapshot = new Uint8Array(bytes).slice();
  const digest = [...new Uint8Array(await crypto.subtle.digest('SHA-256', snapshot))]
    .map(value => value.toString(16).padStart(2, '0')).join('');
  if (digest !== REFERENCE_GATE.artifactSha256) throw new Error('Reference display artifact identity differs from approval.');
  const result = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(snapshot));
  if (result.schema_version !== 'reference-diameter-profile/0.1'
      || result.notice !== REFERENCE_NOTICE || result.mask_origin !== 'reference_annotation'
      || result.validation_status !== 'unvalidated') throw new Error('Unsupported reference display.');
  return result;
}

export function createReferenceProfilesApi(client) {
  return async () => {
    let response;
    try {
      response = await client.get('/research/reference-profiles', { responseType: 'arraybuffer' });
    } catch (error) {
      if (error.response?.status === 503) throw new Error('Approved reference profile evidence unavailable or identity check failed.', { cause: error });
      throw error;
    }
    return validateReferenceBytes(response.data);
  };
}
