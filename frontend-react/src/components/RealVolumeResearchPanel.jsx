import {useEffect, useRef, useState} from 'react';
import {useAuth} from '../context/AuthContext';
import {analyzeRealVolumeResearch} from '../api/real-volume-research.js';

export default function RealVolumeResearchPanel() {
  const {user} = useAuth();
  const [ctVolume, setCtVolume] = useState(null);
  const [vesselMask, setVesselMask] = useState(null);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [fileEpoch, setFileEpoch] = useState(0);
  const generation = useRef(0);
  const controller = useRef(null);

  useEffect(() => {
    const invalidateForSession = () => {
      generation.current += 1;
      controller.current?.abort();
      controller.current = null;
      setCtVolume(null); setVesselMask(null); setResult(null); setError(''); setBusy(false); setFileEpoch(value => value + 1);
    };
    const stopRequest = () => {
      generation.current += 1;
      controller.current?.abort();
      controller.current = null;
    };
    window.addEventListener('storage', invalidateForSession);
    window.addEventListener('vascuai:unauthorized', invalidateForSession);
    return () => {
      stopRequest();
      window.removeEventListener('storage', invalidateForSession);
      window.removeEventListener('vascuai:unauthorized', invalidateForSession);
    };
  }, [user?.id, user?.role]);

  function selectFile(setter) {
    return event => {
      generation.current += 1;
      controller.current?.abort();
      controller.current = null;
      setter(event.target.files?.[0] || null);
      setResult(null); setError(''); setBusy(false);
    };
  }

  async function analyze() {
    const id = ++generation.current;
    const token = localStorage.getItem('vascuai_token');
    const request = new AbortController();
    controller.current?.abort(); controller.current = request;
    setBusy(true); setError(''); setResult(null);
    const current = () => generation.current === id && token === localStorage.getItem('vascuai_token') && !request.signal.aborted;
    try {
      const value = await analyzeRealVolumeResearch({ctVolume, vesselMask, signal: request.signal});
      if (current()) setResult(value);
    } catch (failure) {
      if (current()) setError(failure?.message || 'Real-volume analysis failed.');
    } finally {
      if (current()) setBusy(false);
    }
  }

  function exportResult() {
    if (!result) return;
    const blob = new Blob([JSON.stringify(result, null, 2)], {type: 'application/json'});
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url; link.download = 'vascuai-real-volume-research-qc.json'; link.click();
    URL.revokeObjectURL(url);
  }

  return <section className="card" aria-labelledby="real-volume-research-title">
    <h2 id="real-volume-research-title">Real-volume research QC</h2>
    <p><strong>Separate from synthetic phantom analysis.</strong> Upload a 3D CT NIfTI and matching binary vessel mask. Files are processed ephemerally and not saved. The synthetic CNN and Grad-CAM are never used here.</p>
    <p>Current ImageCAS masks are coronary-artery segmentation annotations with unresolved mask spatial units and unverified lumen semantics. This workflow can verify the pair and report cautious topology evidence; it cannot claim lesion candidates or lumen measurements from those masks.</p>
    <div className="form-grid">
      <label>CT volume (.nii or .nii.gz)<input key={`ct-${fileEpoch}`} className="form-input" type="file" accept=".nii,.nii.gz" onChange={selectFile(setCtVolume)}/></label>
      <label>Matching binary vessel mask (.nii or .nii.gz)<input key={`mask-${fileEpoch}`} className="form-input" type="file" accept=".nii,.nii.gz" onChange={selectFile(setVesselMask)}/></label>
    </div>
    <div className="page-actions">
      <button className="btn btn-primary" type="button" disabled={busy || !ctVolume || !vesselMask} onClick={analyze}>Validate and analyze pair</button>
      {busy && <span role="status">Validating source files and mask geometry…</span>}
    </div>
    {error && <p role="alert">{error}</p>}
    {!result && !busy && <p>No real-volume analysis result. No findings are assumed.</p>}
    {result && <div aria-live="polite">
      <h3>Ephemeral research result: {result.status}</h3>
      <p>{result.notice}</p>
      <dl>
        <dt>CT SHA-256</dt><dd>{result.provenance.ct_sha256}</dd>
        <dt>Mask file SHA-256</dt><dd>{result.provenance.mask_file_sha256}</dd>
        <dt>Shape IJK</dt><dd>{result.geometry.shape_ijk.join(' × ')}</dd>
        <dt>Orientation</dt><dd>{result.geometry.orientation.join(' / ')}</dd>
        <dt>CT spacing (mm)</dt><dd>{result.geometry.voxel_spacing_mm?.join(' / ') ?? 'Unavailable: source units are not known'}</dd>
        <dt>Mask foreground voxels</dt><dd>{result.segmentation.foreground_voxels}</dd>
        <dt>Connected components (26-neighbor)</dt><dd>{result.segmentation.component_count_26}</dd>
        <dt>Experimental digital centerline</dt><dd>{result.centerline.status}</dd>
        <dt>Candidate localization</dt><dd>Unavailable — mask lumen semantics are not verified</dd>
        <dt>Reference/minimum lumen measurement</dt><dd>Unavailable</dd>
        <dt>Percentage narrowing / provisional severity</dt><dd>Unavailable; no values inferred</dd>
        <dt>Clinical/training authorization</dt><dd>false / false</dd>
      </dl>
      {result.centerline.reasons?.length > 0 && <p role="note">Centerline abstention reasons: {result.centerline.reasons.join(', ')}.</p>}
      <button className="btn btn-ghost" type="button" onClick={exportResult}>Export QC research JSON</button>
    </div>}
  </section>;
}
