import { useMemo, useState } from 'react';
import 'chart.js/auto';
import { Line } from 'react-chartjs-2';
import AppShell from '../components/AppShell';
import { PageHeader, Panel, Loading, ErrorState } from '../components/ui';
import { useRemote } from '../hooks/useRemote';
import { loadReferenceProfiles } from '../api/reference-profiles';
import { REFERENCE_GATE, REFERENCE_NOTICE } from '../api/reference-profiles-contract';

function Profile({ data }) {
  const [caseId, setCaseId] = useState('401');
  const [side, setSide] = useState('left');
  const rows = useMemo(() => data.sections.filter(row => row.dataset_case_id === caseId && row.side === side), [data, caseId, side]);
  const chart = useMemo(() => ({ datasets: [...new Set(rows.map(row => row.branch))].map((branch, index) => ({
    label: branch, data: rows.filter(row => row.branch === branch).map(row => ({ x: row.s_mm, y: row.diameter_mm })),
    borderColor: `hsl(${index * 67 % 360} 60% 35%)`, borderWidth: 2, pointRadius: 0,
    spanGaps: false, tension: 0,
  })) }), [rows]);
  const missing = rows.filter(row => row.diameter_mm === null);
  return <>
    <Panel title="Supplied reference centerline profiles" description="Dataset identifiers, not application case IDs. No live model or patient analysis.">
      <div className="page-actions">
        <label>Training dataset case <select value={caseId} onChange={event => setCaseId(event.target.value)}>{['401', '402', '404'].map(id => <option key={id}>{id}</option>)}</select></label>
        <label>Supplied tree <select value={side} onChange={event => setSide(event.target.value)}><option value="left">Left</option><option value="right">Right</option></select></label>
      </div>
      <Line data={chart} options={{ animation: false, parsing: false, scales: {
        x: { type: 'linear', title: { display: true, text: 'Arc length within supplied polyline (mm; not assumed proximal)' } },
        y: { title: { display: true, text: 'Reference area-equivalent diameter (mm)' }, beginAtZero: true },
      }, plugins: { title: { display: true, text: REFERENCE_NOTICE } } }} role="img" aria-label={`${REFERENCE_NOTICE}; dataset ${caseId}, ${side} tree`} />
      <p>{rows.length} supplied sections; {missing.length} unavailable. Every branch retained; unavailable samples remain gaps.</p>
      {missing.map(row => <p key={`${row.branch}-${row.point_id}`}>{row.branch}, {row.s_mm.toFixed(2)} mm: {row.reason}</p>)}
      <details><summary>Accessible numeric profile table (unvalidated reference only)</summary>
        <div className="table-wrapper"><table className="data-table"><caption>{REFERENCE_NOTICE}</caption>
          <thead><tr><th>Branch</th><th>Arc length (mm)</th><th>Diameter (mm)</th><th>Status / reason</th></tr></thead>
          <tbody>{rows.map(row => <tr key={`${row.branch}-${row.point_id}`}><td>{row.branch}</td><td>{row.s_mm.toFixed(3)}</td><td>{row.diameter_mm === null ? 'Unavailable' : row.diameter_mm.toFixed(3)}</td><td>{row.reason || row.status}</td></tr>)}</tbody>
        </table></div>
      </details>
    </Panel>
    <Panel title="Provenance and limits">
      <p>ImageCAS-X v2 annotations by Kit M. Bransby and Rasmus R. Paulsen, CC BY 4.0. <a href="https://doi.org/10.5281/zenodo.23562647">Dataset record and attribution</a>.</p>
      <p>Nearest-neighbor reference mask plane; 8-connected origin component; D = 2√(area/π). No smoothing or hole filling. Other components do not enter this point estimate.</p>
      <p>No calibrated uncertainty, validated resolution gate, anatomical registration claim, stenosis percentage, severity or clinical confidence.</p>
      <p>Display approval: {REFERENCE_GATE.id}. Artifact SHA-256: <code>{REFERENCE_GATE.artifactSha256}</code>. Method SHA-256: <code>{REFERENCE_GATE.methodSha256}</code>.</p>
      <p>The artifact retains its original pre-approval generation state. This narrowly scoped display approval is separate from the empty validated clinical registry.</p>
    </Panel>
  </>;
}

export default function ReferenceProfiles() {
  const remote = useRemote(loadReferenceProfiles);
  return <AppShell><PageHeader eyebrow="REFERENCE RESEARCH" title="Reference diameter profiles" description="Three fixed Split-4 Training cases; supplied annotations only." />
    <div className="notice" role="note"><strong>{REFERENCE_NOTICE}</strong></div>
    {remote.loading ? <Loading label="Checking approved reference evidence…" /> : remote.error ? <ErrorState error={remote.error} retry={remote.reload} /> : <Profile data={remote.data} />}
  </AppShell>;
}
