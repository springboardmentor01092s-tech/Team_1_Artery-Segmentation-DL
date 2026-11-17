import { useCallback, useState } from 'react';
import { Link } from 'react-router-dom';
import { ChartNoAxesCombined, RefreshCw } from 'lucide-react';
import AppShell from '../components/AppShell';
import { PageHeader, Panel, Loading, ErrorState, EmptyState, Metadata } from '../components/ui';
import { useRemote } from '../hooks/useRemote';
import { evaluationsApi } from '../api/evaluations';
import { METRICS } from '../api/evaluations-contract';

const score = (value) => value == null ? 'Unavailable' : value.toFixed(6);
const label = (row) => `${row.metadata.model.display_name} · ${row.checkpoint_sha256.slice(0, 12)} · ${row.id.slice(0, 8)}`;

function MetricTable({ rows }) {
  return <div className="table-wrapper"><table className="data-table">
    <caption>Recorded segmentation metrics (0–1)</caption>
    <thead><tr><th scope="col">Record</th>{METRICS.map((m) => <th scope="col" key={m}>{m}</th>)}</tr></thead>
    <tbody>{rows.map(([name, values, identity]) => <tr key={identity ?? name}><th scope="row">{name}</th>{METRICS.map((m) => <td key={m}>{score(values?.[m])}</td>)}</tr>)}</tbody>
  </table></div>;
}

function Provenance({ row }) {
  const metadata = row.metadata;
  return <Metadata items={[
    ['Evaluation ID', row.id], ['Source artifact', row.source_artifact_id],
    ['Model', metadata.model.display_name], ['Architecture', metadata.model.architecture],
    ['Checkpoint SHA-256', row.checkpoint_sha256], ['Prediction threshold', row.threshold],
    ['Validation split source', metadata.validation_split_source],
    ['Imported training-run reference', metadata.checkpoint.training_run_id],
    ['Reported training steps (metadata, not verified optimizer count)', metadata.checkpoint.reported_training_steps],
    ['Metric definitions', metadata.metric_definitions], ['Recorded provenance', metadata.provenance],
  ]} />;
}

function RunHistory({ modelId }) {
  const [offset, setOffset] = useState(0);
  const loader = useCallback(() => evaluationsApi.runs(modelId, offset), [modelId, offset]);
  const remote = useRemote(loader);
  return <Panel title="Imported model run history" description="Recorded offline metadata; this is not a training runner or serving registry.">
    {remote.loading ? <Loading /> : remote.error ? <ErrorState error={remote.error} retry={remote.reload} /> : <>
      <Metadata items={remote.data.training_runs.map((run) => [run.id, {
        reference: run.training_run_id, checkpoint_sha256: run.checkpoint_sha256,
        reported_training_steps: run.reported_training_steps, record_origin: run.record_origin,
      }])} />
      {!remote.data.training_runs.length && <p>No accessible run references on this page.</p>}
      <p>{remote.data.evaluations.length} accessible evaluations on this page. Training provenance may remain unresolved.</p>
      <Pager offset={offset} next={remote.data.pagination.next_offset} capped={remote.data.pagination.offset_limit_reached} change={setOffset} />
    </>}
  </Panel>;
}

function Pager({ offset, next, capped, change }) {
  return <div className="page-actions">
    <button className="btn btn-ghost" disabled={offset === 0} onClick={() => change(Math.max(0, offset - 20))}>Previous page</button>
    <span>Page {Math.floor(offset / 20) + 1}</span>
    <button className="btn btn-ghost" disabled={next == null} onClick={() => change(next)}>Next page</button>
    {capped && <p>Pagination limit reached. Narrow the query before continuing.</p>}
  </div>;
}

function SectionStatus({ evaluationId, caseId }) {
  const loader = useCallback(() => evaluationsApi.sections(evaluationId, caseId), [evaluationId, caseId]);
  const remote = useRemote(loader);
  return remote.loading ? <Loading /> : remote.error ? <ErrorState error={remote.error} retry={remote.reload} /> : <div className="notice" role="status">
    <div><strong>Stenosis measurement unavailable</strong>
      <p>No validated resolution gate. No quantitative stenosis measurement is reported.</p>
      <Metadata items={[
        ['Status', remote.data.measurement_status], ['Section records', remote.data.section_data_status],
        ['Mask origin', remote.data.mask_provenance?.origin], ['Mask SHA-256', remote.data.mask_provenance?.mask_sha256],
      ]} />
    </div>
  </div>;
}

function EvaluationDetail({ id }) {
  const [sectionCase, setSectionCase] = useState(null);
  const loader = useCallback(async () => {
    const [summary, cases] = await Promise.all([evaluationsApi.summary(id), evaluationsApi.cases(id)]);
    if ([...summary.case_ids].sort((a,b) => a-b).join(',') !== cases.cases.map((r) => r.case_id).sort((a,b) => a-b).join(',')) {
      throw new Error('Summary and case membership differ. Refresh the recorded evidence.');
    }
    return { summary, cases };
  }, [id]);
  const remote = useRemote(loader);
  if (remote.loading) return <Loading />;
  if (remote.error) return <ErrorState error={remote.error} retry={remote.reload} />;
  const { summary, cases } = remote.data;
  return <>
    <Panel title="Segmentation evaluation" action={<button className="btn btn-ghost" onClick={remote.reload}><RefreshCw size={14} /> Refresh evaluation</button>}>
      <p>Headline: unweighted macro-average across cases, with undefined metrics omitted per metric. {summary.included_case_count} of {summary.case_count} cases included.</p>
      <MetricTable rows={[
        ['Macro-average (headline)', summary.macro_metrics],
        ...(summary.pooled_micro_metrics ? [['Pooled micro-average (separate)', summary.pooled_micro_metrics]] : []),
      ]} />
      <p>Pooled metrics: {summary.pooled_status}. Undefined denominators remain null, never zero.</p>
      <Metadata items={METRICS.map((m) => [`${m} macro denominator`, summary.macro_denominators[m]])} />
      <Provenance row={summary} />
    </Panel>
    <Panel title="Case-wise segmentation results" description="Dataset IDs and application case IDs are distinct. Excluded cases remain visible.">
      <MetricTable rows={cases.cases.map((row) => [`Case ${row.case_id} · dataset ${row.dataset_case_id}`, row.metrics])} />
      <Metadata items={[
        ['Metric formulas', cases.metric_formulas], ['Undefined-value policy', cases.undefined_macro_policy],
        ['Exclusions', summary.exclusions.length ? summary.exclusions : 'None recorded'],
      ]} />
      {cases.cases.map((row) => <details key={row.case_id}>
        <summary>Case {row.case_id} artifact provenance</summary>
        <Metadata items={[
          ['Reference SHA-256', row.reference_sha256], ['Prediction SHA-256', row.prediction_sha256],
          ['Exclusion reason', row.exclusion_reason], ['Confusion counts', row.confusion_counts], ['Mask provenance', row.mask_provenance],
        ]} />
        <button className="btn btn-ghost" onClick={() => setSectionCase(row.case_id)}>View stenosis availability for case {row.case_id}</button>
      </details>)}
      {sectionCase !== null && <SectionStatus key={sectionCase} evaluationId={id} caseId={sectionCase} />}
    </Panel>
    <RunHistory key={summary.model_id} modelId={summary.model_id} />
  </>;
}

function ComparisonResult({ ids }) {
  const key = ids.join(',');
  const loader = useCallback(() => evaluationsApi.compare(key.split(',')), [key]);
  const remote = useRemote(loader);
  if (remote.loading) return <Loading />;
  if (remote.error) return <ErrorState error={remote.error} retry={remote.reload} />;
  const result = remote.data;
  return <Panel title="Recorded evaluation comparison">
    <p>Exact case membership matches ({result.case_ids.length} cases). No model winner is inferred.</p>
    <MetricTable rows={result.evaluations.map((row) => [label(row), row.macro_metrics, row.id])} />
    <Metadata items={[
      ['Metric definitions match', result.metric_definitions_match],
      ['Reference artifacts match', result.reference_artifacts_match], ['Exclusions match', result.exclusions_match],
    ]} />
    {(!result.metric_definitions_match || !result.reference_artifacts_match || !result.exclusions_match)
      && <p className="notice">Protocols differ. These scores do not establish a fair model-selection comparison.</p>}
    {result.evaluations.map((row) => <details key={row.id}><summary>{label(row)} provenance and denominators</summary>
      <Provenance row={row} /><Metadata items={[
        ['Included cases', row.included_case_count], ['Macro denominators', row.macro_denominators],
        ['Exclusions', row.exclusions], ['Pooled micro metrics (separate)', row.pooled_micro_metrics],
      ]} />
    </details>)}
  </Panel>;
}

export default function Evaluations({ comparison = false, initialTab }) {
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState('');
  const [compareIds, setCompareIds] = useState([]);
  const [requested, setRequested] = useState(null);
  const loader = useCallback(() => evaluationsApi.list(offset), [offset]);
  const remote = useRemote(loader);
  return <AppShell breadcrumbs={[{ label: 'Research' }, { label: comparison ? 'Comparison' : 'Evaluation' }]}>
    <PageHeader eyebrow="RECORDED EVALUATION EVIDENCE" title={comparison ? 'Compare recorded evaluations.' : 'Evidence makes the difference.'}
      description="Real imported segmentation results, with case membership, metric definitions and provenance.">
      <Link className="btn btn-ghost" to={comparison ? '/evaluation' : '/models/compare'}>{comparison ? 'Evaluation workspace' : 'Model comparison'}</Link>
    </PageHeader>
    <p className="notice">Research prototype. No clinical validation or quantitative stenosis capability is established. Imported records do not certify a model.</p>
    {initialTab === 'Stenosis' && <p className="notice">Stenosis evaluation measurements remain unavailable without a validated provider and gate. Segmentation scores below are a separate task.</p>}
    <Panel title="Accessible imported evaluations" action={<button className="btn btn-ghost" onClick={() => {
      setSelected(''); setCompareIds([]); setRequested(null); remote.reload();
    }}><RefreshCw size={14} /> Refresh list</button>}>
      {remote.loading ? <Loading /> : remote.error ? <ErrorState error={remote.error} retry={remote.reload} /> : <>
        {!remote.data.items.length ? <EmptyState icon={ChartNoAxesCombined} title={offset === 0 ? 'No evaluations imported yet' : 'No evaluations on this page'}
          description="Only imported evaluations whose cases you can access appear here. Import is a separate authorized workflow." /> : comparison ? <>
          <fieldset><legend>Select 2–10 evaluations (selection persists across pages)</legend>
            {remote.data.items.map((row) => <label key={row.id} className="preference-row">
              <input type="checkbox" checked={compareIds.includes(row.id)} disabled={!compareIds.includes(row.id) && compareIds.length >= 10}
                onChange={(event) => { setRequested(null); setCompareIds((ids) => event.target.checked ? [...ids, row.id] : ids.filter((id) => id !== row.id)); }} />{label(row)}
            </label>)}
          </fieldset>
          <button className="btn btn-primary" disabled={compareIds.length < 2} onClick={() => setRequested([...compareIds])}>Compare {compareIds.length} evaluations</button>
          <button className="btn btn-ghost" onClick={() => { setCompareIds([]); setRequested(null); }}>Clear selection</button>
        </> : <>
          <label className="form-label" htmlFor="evaluation-record">Evaluation record</label>
          <select id="evaluation-record" className="form-select" value={selected} onChange={(e) => setSelected(e.target.value)}>
            <option value="">Select an evaluation</option>
            {remote.data.items.map((row) => <option key={row.id} value={row.id}>{label(row)}</option>)}
          </select>
        </>}
        <Pager offset={offset} next={remote.data.next_offset} capped={remote.data.offset_limit_reached}
          change={(page) => { setOffset(page); setSelected(''); }} />
      </>}
    </Panel>
    {!comparison && selected && !remote.loading && !remote.error && <EvaluationDetail key={selected} id={selected} />}
    {comparison && requested && <ComparisonResult key={requested.join(',')} ids={requested} />}
  </AppShell>;
}

export function ModelComparison() { return <Evaluations comparison />; }
