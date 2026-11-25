import { useRef, useState } from 'react';
import { Panel } from './ui';
import { useAuth } from '../context/AuthContext';
import { evaluationsApi } from '../api/evaluations';

export default function EvaluationImport({ onImported }) {
  const { isRole } = useAuth();
  const [file, setFile] = useState(null);
  const [upload, setUpload] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [done, setDone] = useState(false);
  const [fileKey, setFileKey] = useState(0);
  const lock = useRef(false);
  if (!isRole('Admin', 'DataScientist')) return null;

  async function submit(kind) {
    if (lock.current) return;
    lock.current = true; setBusy(true); setError('');
    try {
      if (kind === 'upload') setUpload(await evaluationsApi.upload(file));
      else {
        const result = await evaluationsApi.importArtifact(upload);
        setDone(true); onImported(result);
      }
    } catch (cause) {
      const status = cause.response?.status;
      const detail = typeof cause.response?.data?.detail === 'string' ? cause.response.data.detail : cause.message;
      const guidance = kind === 'import'
        ? 'Retry uses this same stored artifact ID; it will not upload another file. A 409 conflict requires reviewing the recorded metadata.'
        : 'No automatic retry was made. If the response was lost, the upload may have succeeded; ask the operator to reconcile it before uploading again.';
      setError(`${detail || 'The operation could not be verified.'}${status ? ` (HTTP ${status})` : ''} ${guidance}`);
    } finally { lock.current = false; setBusy(false); }
  }

  return <Panel title="Import existing offline evaluation" description="Admin and Data Scientist only. This stores recorded evidence; it does not run a model.">
    <p>Use a versioned offline-evaluation/1.0 JSON document, at most 2 MiB. Its case_id fields must be real application case IDs bound to the verified source CTs. Dataset numbers alone are not application IDs. The server validates metadata, metrics and case access.</p>
    <label className="form-label" htmlFor="evaluation-document">Offline evaluation JSON</label>
    <input key={fileKey} id="evaluation-document" type="file" accept=".json,application/json" disabled={busy || Boolean(upload)} onChange={event => {
      setFile(event.target.files?.[0] ?? null); setError(''); setDone(false);
    }} />
    {!upload ? <button className="btn btn-primary" disabled={busy || !file} onClick={() => submit('upload')}>Upload evaluation artifact</button> : <>
      <p role="status" style={{ overflowWrap: 'anywhere' }}>Artifact stored and verified: {upload.artifact.id}. SHA-256: {upload.artifact.sha256}. {upload.case_ids.length} cases.</p>
      <button className="btn btn-primary" disabled={busy || done} onClick={() => submit('import')}>Import stored evaluation</button>
      <button className="btn btn-ghost" disabled={busy} onClick={() => { setUpload(null); setFile(null); setFileKey(value => value + 1); setDone(false); setError(''); }}>Choose another document</button>
      <p>Choosing another document preserves this stored artifact and any imported evaluation. It does not delete evidence.</p>
    </>}
    {busy && <p role="status">Verifying the operation…</p>}
    {done && <p role="status">Evaluation imported. The discovery list has been refreshed; select the recorded evaluation to inspect it.</p>}
    {error && <p className="notice error" role="alert">{error}</p>}
  </Panel>;
}
