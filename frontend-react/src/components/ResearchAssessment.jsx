import { useLayoutEffect, useRef, useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { blankResearchCalipers, createResearchAssessment, researchAssessmentBlob, RESEARCH_NOTICE,
  validateResearchAssessment } from '../lib/research-assessment';
import { manualNativeLandmark } from '../lib/review-annotation';
import { saveArtifact } from '../lib/segmentation';
import ResearchEvidence from './ResearchEvidence';

export default function ResearchAssessment(props) {
  const {user} = useAuth();
  const key = JSON.stringify([user?.id,user?.role,props.segmentation.id,props.segmentation.metadata,props.preview]);
  return <Workspace key={key} {...props} owner={user}/>;
}

function Workspace({preview,geometry,segmentation,mask,owner,onLocate}) {
  const [result,setResult] = useState(null), [error,setError] = useState(''), [busy,setBusy] = useState(false);
  const [fields,setFields] = useState({minimum_start_ijk:'',minimum_end_ijk:'',reference_start_ijk:'',reference_end_ijk:'',method_evidence:''});
  const session = useRef({alive:false,generation:0,operation:0});
  useLayoutEffect(() => {
    const state = session.current; state.alive=true; state.generation++;
    const invalidate = event => {
      if (event.type==='storage' && event.key!==null && event.key!=='vascuai_token') return;
      state.generation++; state.operation++; setResult(null); setBusy(false); setError('Session changed. Reopen the current CT before continuing.');
    };
    window.addEventListener('storage',invalidate); window.addEventListener('vascuai:unauthorized',invalidate);
    return () => {state.alive=false;state.generation++;window.removeEventListener('storage',invalidate);window.removeEventListener('vascuai:unauthorized',invalidate);};
  },[owner]);
  const context = {geometry,segmentation,mask};
  async function perform(action) {
    const state=session.current, generation=state.generation, operation=++state.operation, token=localStorage.getItem('vascuai_token');
    const current = () => state.alive && generation===state.generation && operation===state.operation && token===localStorage.getItem('vascuai_token');
    const check = () => {if (!current() || !token || !owner) throw new Error('Session changed; no research result accepted.');};
    setBusy(true);setError('');
    try {check();await action(check);}
    catch (failure) {if(current()) setError(failure.message);}
    finally {if(state.alive && operation===state.operation){setBusy(false);if(!current()){setResult(null);setError('Session changed; no research result accepted.');}}}
  }
  function readCalipers() {
    const input=blankResearchCalipers(),source={...geometry,units:geometry.units??geometry.world_unit};
    for (const key of Object.keys(input)) input[key]=key==='method_evidence'?fields[key]:fields[key].trim()?manualNativeLandmark(fields[key],source):null;
    return input;
  }
  const run = () => perform(async check => {
    const next=await createResearchAssessment(preview,context,readCalipers());check();setResult(next);
  });
  const download = () => perform(async check => {
    const blob=await researchAssessmentBlob(result,context);check();
    saveArtifact({blob,filename:`vascuai-case-${segmentation.case_id}-provisional-research.json`});
  });
  const locate = (role,branchId,id) => perform(async check => {
    const checked=await validateResearchAssessment(result,context);check();
    const proposal=checked.document.records.find(item=>item.record.role===role)?.record.evidence.find(branch=>branch.branch_id===branchId)?.proposals.find(item=>item.proposal_id===id);
    if(!proposal)throw new Error('Research proposal is no longer available.');
    onLocate(proposal);
  });
  const locateSample = (branchId,index) => perform(async check => {
    const checked=await validateResearchAssessment(result,context);check();
    const row=checked.document.profile.branches.find(branch=>branch.branch_id===branchId)?.sections[index];
    if(!row)throw new Error('Research sample no longer available.');
    onLocate(row);
  });
  function restore(event) {
    const file=event.target.files?.[0];event.target.value='';if(!file)return;
    setResult(null);
    return perform(async check => {
      if(!file.size || file.size>2*1024*1024)throw new Error('Standalone research JSON must be nonempty and at most 2 MiB.');
      const text=await file.text();check();
      const next=await validateResearchAssessment(JSON.parse(text),context);check();
      setFields(Object.fromEntries(Object.entries(next.document.manual_caliper_input).map(([key,value])=>[key,Array.isArray(value)?value.join(', '):value??''])));
      setResult(next);
    });
  }
  const record=result?.document.records;
  return <section className="stack no-print" aria-label="Provisional research assessments">
    <h3>Simulated R1 / R2 / R3 research assessments</h3>
    <p className="notice"><strong>{RESEARCH_NOTICE}</strong>. No qualified human or trained stenosis reviewer is simulated as real.</p>
    <p>R1 uses bidirectional median interpolation. R2 uses the smaller directional mean. Both share one predicted artery mask and sampled profile; their errors are correlated. R3 preserves disagreements, without voting or clinical adjudication.</p>
    <p>No calibrated model confidence or stenosis attribution is available. Geometry support is not Grad-CAM.</p>
    <details><summary>Optional unverified caliper arithmetic</summary>
      <p>Enter original native IJK endpoints only after inspecting the CT. The tool checks geometry and arithmetic, not plane selection, anatomical alignment or clinical validity. Blank values stay unavailable. These inputs never enter expert drafts or clinical reports.</p>
      <div className="form-grid">{Object.keys(fields).filter(key=>key!=='method_evidence').map(key=><label key={key} style={{display:'grid',gap:'.5rem'}}>{key.replaceAll('_',' ')}<input className="form-input" maxLength={200} aria-label={`Research ${key}`} value={fields[key]} disabled={busy} placeholder="I, J, K (optional)" onChange={e=>{setFields({...fields,[key]:e.target.value});setResult(null);}}/></label>)}</div>
      <label style={{display:'grid',gap:'.5rem',marginBlock:'1rem'}}>Plane and reference-selection evidence<textarea className="form-input" aria-label="Research method evidence" maxLength={1000} value={fields.method_evidence} disabled={busy} onChange={e=>{setFields({...fields,method_evidence:e.target.value});setResult(null);}}/></label>
    </details>
    <div className="page-actions"><button type="button" className="btn btn-ghost" disabled={busy} onClick={run}>Run provisional research assessments</button>
      <label style={{display:'grid',gap:'.5rem'}}>Restore standalone research JSON<input className="form-input" aria-label="Restore standalone research JSON" type="file" accept=".json,application/json" disabled={busy} onChange={restore}/></label>
      <button type="button" className="btn btn-ghost" disabled={busy||!result} onClick={download}>Download standalone research JSON</button></div>
    {busy&&<p role="status">Revalidating source, geometry, assessment evidence and hashes…</p>}
    {error&&<p role="alert" className="notice error">{error}</p>}
    {!result&&!busy&&<p>No provisional assessment accepted. Nothing is saved to the server.</p>}
    {result&&<>
      <p>Assessment checksum: <code style={{overflowWrap:'anywhere'}}>{result.sha256}</code>. Hash-linked local snapshots are tamper-evident, not authenticated immutable server submissions.</p>
      <p>Model: {result.document.model_provenance.architecture??'Unavailable in saved metadata'}. Confidence: unavailable (not calibrated). Clinical authorization: false. Training authorization: false.</p>
      <p>Manual caliper status: {result.document.manual_caliper_result.status}. {result.document.manual_caliper_result.reason}</p>
      <p>Caliper formula: 100 × (1 − D_min / D_reference). Distances use original IJK endpoints transformed by the CT affine into RAS millimetres; plane/reference appropriateness is unverified.</p>
      <p>Minimum endpoints: {result.document.manual_caliper_input.minimum_start_ijk?.join(', ')??'Unavailable'} → {result.document.manual_caliper_input.minimum_end_ijk?.join(', ')??'Unavailable'}. Reference endpoints: {result.document.manual_caliper_input.reference_start_ijk?.join(', ')??'Unavailable'} → {result.document.manual_caliper_input.reference_end_ijk?.join(', ')??'Unavailable'}.</p>
      {result.document.manual_caliper_result.diagnostic_diameter_reduction_percent!==null&&<p>Unverified arithmetic only: {result.document.manual_caliper_result.diagnostic_diameter_reduction_percent.toFixed(3)}% diameter reduction. Not a clinically validated stenosis measurement.</p>}
      {record.slice(0,2).map(item=><div key={item.record.role}><h4>{item.record.role}: {item.record.procedure}</h4>
        {item.record.evidence.map(branch=><div key={branch.branch_id}><p>{branch.branch_id}: {branch.evaluable_sections} evaluable, {branch.unassessable_sections} unassessable, {branch.proposals.length} proposals. No proposal does not establish normal anatomy.</p>
          <div className="table-wrapper"><table className="data-table"><caption>Unverified {item.record.role} candidate proposals</caption><thead><tr><th>Proposal</th><th>Center IJK</th><th>Branch interval (mm)</th><th>Area-equivalent diameter (mm)</th><th>Reference equivalent (mm)</th><th>Diagnostic reduction (%)</th></tr></thead><tbody>
            {branch.proposals.map(proposal=><tr key={proposal.proposal_id}><td><button className="btn btn-ghost btn-sm" type="button" disabled={busy} onClick={()=>locate(item.record.role,branch.branch_id,proposal.proposal_id)}>Locate {proposal.proposal_id}</button><br/>Artery unknown</td><td>{proposal.center_ijk.map(n=>n.toFixed(2)).join(', ')}</td><td>{proposal.interval_s_mm.map(n=>n.toFixed(2)).join(' – ')}</td><td>{proposal.research_measurement.minimum_area_equivalent_diameter_mm.toFixed(3)}</td><td>{proposal.research_measurement.reference_area_equivalent_diameter_mm.toFixed(3)}</td><td>{proposal.research_measurement.diagnostic_diameter_reduction_percent.toFixed(3)} (unvalidated)</td></tr>)}</tbody></table></div>
        </div>)}</div>)}
      <h4>R3: provisional comparison</h4>
      {record[2].record.evidence.map(branch=><p key={branch.branch_id}>{branch.branch_id}: {branch.sections.filter(row=>row.status==='disagreement_unresolved').length} unresolved section disagreements; {branch.sections.filter(row=>row.status==='unassessable').length} unassessable. Both original proposal lists retained.</p>)}
      <p>R1/R2 snapshots cannot be edited; re-running creates a new local snapshot. Save separate downloads to retain versions. No persistent AI agent or server history is created. Severity and clinical outputs remain unavailable.</p>
      <ResearchEvidence key={result.sha256} value={result} onLocate={locateSample} busy={busy}/>
    </>}
  </section>;
}
