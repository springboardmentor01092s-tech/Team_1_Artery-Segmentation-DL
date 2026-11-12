import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { EXPERIMENT_NOTICE, MAX_PREVIEW_BYTES, experimentalMaskIdentity, navigateExperimentalCandidate,
  projectExperimentalCandidates, validateExperimentalPreview } from '../lib/experimental-candidates';

// Opt-in local file preview. No API, persistence, analytics, report or export path.
export default function ExperimentalCandidatePreview({ viewer, geometry, maskBuffer, segmentation, layer, location, view, onSlices }) {
  const [preview, setPreview] = useState(null), [selected, setSelected] = useState(null);
  const [error, setError] = useState(''), [markers, setMarkers] = useState([]), [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);
  const request = useRef(0);
  useEffect(() => () => { request.current++; }, []);
  useEffect(() => {
    if (!preview || view === 'mask3d') return;
    const project = () => {
      try { setMarkers(projectExperimentalCandidates(viewer, preview, selected)); }
      catch (failure) { setMarkers([]); setError(failure.message); }
    };
    const frame = requestAnimationFrame(project), observer = new ResizeObserver(project);
    observer.observe(viewer.canvas);
    return () => { cancelAnimationFrame(frame); observer.disconnect(); };
  }, [viewer, preview, location, view, selected]);

  async function load(event) {
    const file = event.target.files?.[0], version = ++request.current;
    event.target.value = ''; setPreview(null); setMarkers([]); setSelected(null); setError('');
    if (!file) return;
    setBusy(true);
    try {
      if (!maskBuffer) throw new Error('Experimental preview is limited to masks with at most 4,000,000 voxels.');
      if (!file.size || file.size > MAX_PREVIEW_BYTES) throw new Error('Local preview must be a nonempty JSON file no larger than 2 MiB.');
      const value = JSON.parse(await file.text());
      const mask = await experimentalMaskIdentity(maskBuffer, geometry.shape);
      const checked = await validateExperimentalPreview(value, geometry, segmentation, mask);
      if (request.current === version) { setPreview(checked); setSelected(checked.candidates[0]?.candidate_id || null); }
    } catch (failure) { if (request.current === version) setError(failure.message); }
    finally { if (request.current === version) setBusy(false); }
  }
  function select(candidate) {
    try { onSlices(); navigateExperimentalCandidate(viewer, candidate); setSelected(candidate.candidate_id); }
    catch (failure) { setMarkers([]); setError(failure.message); }
  }
  return <details className="card no-print" style={{padding:'1rem'}} onToggle={event => setOpen(event.currentTarget.open)}>
    <summary>Experimental local candidate preview</summary>
    <p className="notice"><strong>{EXPERIMENT_NOTICE}</strong>. Supplied geometry candidates, not confirmed lesions or AI predictions. Measurements unavailable: no validated gate.</p>
    <p>Import a locally prepared research preview bound to this exact predicted artery mask. The file stays in memory; no analysis job, upload, clinical result or export is created. Reference annotations cannot be presented as predictions.</p>
    <label style={{display:'block',marginBlock:'.75rem'}}>Local experimental candidate JSON<input style={{display:'block',marginTop:'.5rem'}} aria-label="Local experimental candidate JSON" type="file" accept=".json,application/json" onChange={load} disabled={busy}/></label>
    {busy && <p role="status">Checking local preview and displayed mask identity…</p>}
    {error && <p className="notice error" role="alert">{error} No experimental findings are accepted.</p>}
    {!preview && !busy && <p>No experimental preview loaded. No findings have been assumed.</p>}
    {preview && <>
      <p>Supplied algorithm: {preview.algorithm.id} / {preview.algorithm.version}. Source role: {preview.source.mask_role}.</p>
      <p className="text-xs" style={{overflowWrap:'anywhere'}}>Mask SHA-256 (canonical array): {preview.source.mask_sha256}<br/>Geometry: {preview.source.geometry_fingerprint}<br/>Parameters: {preview.parameters_sha256}</p>
      <p>All parameters are unvalidated research choices. Area ratio trigger: {preview.parameters.area_ratio_trigger}. This is not a clinical threshold or a measured narrowing percentage.</p>
      <p>Preview state: {preview.status}. {preview.reason || ''} {preview.candidates.length} potential candidates; absence in evaluable sections is not proof of absence of disease.</p>
      <ul>{preview.branches.map(branch => <li key={branch.branch_id}>{branch.branch_id}: {branch.evaluable_sections} evaluable, {branch.abstained_sections} abstained sections.</li>)}</ul>
      <div role="group" aria-label="Experimental candidates">{preview.candidates.map(candidate => <button type="button" className="btn btn-ghost" key={candidate.candidate_id} aria-pressed={selected === candidate.candidate_id} onClick={() => select(candidate)}>Locate experimental {candidate.candidate_id} ({candidate.branch_id})</button>)}</div>
      <p className="text-xs">Orange points = supplied experimental candidate centers on the current 2D slices. Magenta = predicted artery. No reference annotation overlay is introduced. {view === 'mask3d' && 'Experimental points are unavailable in 3D view.'}</p>
    </>}
    {layer && open && preview && view !== 'mask3d' && !error && createPortal(<div className="lesion-marker-layer no-print" aria-label="Experimental candidate locations">{markers.map(marker => {
      const candidate = preview.candidates.find(item => item.candidate_id === marker.id);
      return <button type="button" key={`${marker.id}-${marker.plane}`} className="lesion-marker" style={{left:`${marker.x}%`,top:`${marker.y}%`,background:'#f59e0b',border:'2px dashed #222222'}} aria-label={`Locate ${marker.plane} experimental ${marker.id}`} title={`${EXPERIMENT_NOTICE}: ${marker.id}`} onClick={() => select(candidate)}/>;
    })}</div>, layer)}
  </details>;
}
