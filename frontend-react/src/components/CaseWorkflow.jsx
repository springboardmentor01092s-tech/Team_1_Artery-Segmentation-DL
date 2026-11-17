import { useState } from 'react';
import { Link } from 'react-router-dom';
import { ClipboardCheck, Download, RefreshCw } from 'lucide-react';
import { casesApi } from '../api/cases';
import { downloadCaseWorkflow } from '../lib/exports';
import { formatDate } from '../lib/format';
import { ErrorState, Loading, Metadata, Panel, StatusBadge } from './ui';

const outcomeLabel = value => value === 'accepted_for_research' ? 'Accepted for research workflow' : 'Changes requested';

export default function CaseWorkflow({ caseId, workflow, canReview = false, onRecorded }) {
  const data = workflow.data;
  return <Panel title="Research workflow review" description="A recorded research decision, not clinical validation."
    action={<button type="button" className="btn btn-ghost" onClick={workflow.reload} aria-label="Refresh case workflow"><RefreshCw size={14}/> Refresh</button>}>
    {workflow.loading ? <Loading/> : workflow.error ? <ErrorState error={workflow.error} retry={workflow.reload}/> : !data ?
      <div className="notice" role="status">Workflow evidence is unavailable. Completion cannot be verified.</div> : <>
        <StatusBadge status={data.caseStatus}/>
        <p className="text-sm text-muted">{data.model_analysis.available
          ? `Saved segmentation ${data.model_analysis.run.segmentation_result_id} is current and available.`
          : data.model_analysis.reason}</p>
        <p className="notice">Research review records inspection of a saved output only. It does not establish segmentation accuracy, clinical approval, stenosis findings or a quantitative measurement gate.</p>
        {data.review ? <div role="status" aria-label="Current research review">
          <Metadata items={[
            ['Outcome', outcomeLabel(data.review.outcome)],
            ['Reviewer', `User #${data.review.reviewer_id} (${data.review.reviewer_role})`],
            ['Recorded', formatDate(data.review.reviewed_at, true)],
            ['Saved run', data.review.segmentation_result_id],
          ]}/>
          {data.review.note && <p style={{whiteSpace:'pre-wrap'}}>{data.review.note}</p>}
        </div> : data.review_requires_new_run ?
          <p className="notice error">This run's reviewed evidence changed. Generate and inspect a new segmentation before another review.</p>
          : data.model_analysis.available && canReview ? <ReviewForm key={data.model_analysis.run.segmentation_result_id}
            caseId={caseId} runId={data.model_analysis.run.segmentation_result_id} onRecorded={onRecorded}/>
          : <p className="text-sm text-muted">{canReview ? 'A current saved segmentation is required before review.' : 'Only an authorized Clinician or Admin can record a review.'}</p>}
        <div className="page-actions">
          <Link className="btn btn-ghost" to={`/cases/${caseId}/analysis`}>Inspect saved segmentation</Link>
          <button type="button" className="btn btn-ghost" onClick={() => downloadCaseWorkflow(data)}><Download size={14}/> Workflow JSON</button>
        </div>
        <ReviewHistory reviews={data.review_history}/>
      </>}
  </Panel>;
}

function ReviewForm({ caseId, runId, onRecorded }) {
  const [outcome, setOutcome] = useState('accepted_for_research');
  const [note, setNote] = useState('');
  const [acknowledged, setAcknowledged] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function submit(event) {
    event.preventDefault();
    if (busy || !acknowledged) return;
    setBusy(true); setError('');
    try {
      await casesApi.review(caseId, { segmentation_result_id: runId, outcome, note: note.trim() || null,
        acknowledge_research_only: acknowledged });
      onRecorded?.();
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }
  return <form onSubmit={submit} aria-label="Record research review">
    {error && <div className="notice error" role="alert">{error}</div>}
    <div className="form-group"><label className="form-label" htmlFor="research-review-outcome">Review outcome</label>
      <select id="research-review-outcome" className="form-select" disabled={busy} value={outcome} onChange={event => setOutcome(event.target.value)}>
        <option value="accepted_for_research">Accept for research workflow</option>
        <option value="changes_requested">Request changes</option>
      </select></div>
    <div className="form-group"><label className="form-label" htmlFor="research-review-note">Research review note (no identifying information)</label>
      <textarea id="research-review-note" className="form-textarea" maxLength={1000} required={outcome === 'changes_requested'}
        disabled={busy} value={note} onChange={event => setNote(event.target.value)}/></div>
    <label><input type="checkbox" required checked={acknowledged} disabled={busy} onChange={event => setAcknowledged(event.target.checked)}/>{' '}
      I inspected this saved segmentation. This is research workflow review only, not clinical validation.</label>
    <p className="text-xs text-muted">The reviewer and time are recorded by the server. A decision is immutable for this run; changed outputs require a new run and review.</p>
    <button className="btn btn-primary" disabled={busy || !acknowledged}><ClipboardCheck size={14}/>{busy ? 'Recording review…' : 'Record research review'}</button>
  </form>;
}

function ReviewHistory({ reviews }) {
  if (!reviews.length) return null;
  return <details className="report-integrity-details"><summary>Research review history (latest 20)</summary>
    <ul>{reviews.map(review => <li key={review.id}>
      {outcomeLabel(review.outcome)} · User #{review.reviewer_id} ({review.reviewer_role}) · {formatDate(review.reviewed_at, true)}
      <br/>Run {review.segmentation_result_id} · {review.current ? 'Current evidence' : 'Historical; not approval of current evidence'}
      {review.note && <p style={{whiteSpace:'pre-wrap'}}>{review.note}</p>}
    </li>)}</ul>
  </details>;
}
