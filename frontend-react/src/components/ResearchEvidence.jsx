import {useState} from 'react';
import {evidenceLineSegments,researchEvidenceRows} from '../lib/research-evidence';

const series=[['sampled_area_mm2','Sampled mask area','#222222'],['r1_reference_area_mm2','R1 reference','#1d4ed8'],
  ['r2_reference_area_mm2','R2 reference','#6d28d9'],['r1_trigger_area_mm2','R1 trigger area','#0369a1'],['r2_trigger_area_mm2','R2 trigger area','#a21caf']];
const number=n=>n===null?'Unavailable':n.toFixed(3);

export default function ResearchEvidence({value,onLocate,busy}) {
  const [choice,setChoice]=useState(''),[selection,setSelection]=useState(null);
  const ids=value.document.profile.branches.map(branch=>branch.branch_id);
  const branch=ids.includes(choice)?choice:ids[0];
  if(!branch)return <p>No branch evidence available; no normal-anatomy conclusion.</p>;
  const rows=researchEvidenceRows(value,branch),selected=rows.find(row=>row.index===selection)??rows.find(row=>row.r1_regions.length||row.r2_regions.length)??rows[0];
  const span=rows.at(-1).s_mm-rows[0].s_mm;
  const top=Math.max(1,...rows.flatMap(row=>series.map(([key])=>row[key]??0)))*1.05;
  const x=n=>50+(n-rows[0].s_mm)/span*800,y=n=>245-n/top*210;
  const clipped=range=>[Math.max(range[0],rows[0].s_mm),Math.min(range[1],rows.at(-1).s_mm)];
  return <details className="no-print"><summary>Calculation evidence: profiles, support and disagreements</summary>
    <p>Geometric explanation of the actual recorded procedures, not model attribution, confidence or lesion ground truth. Curves never bridge unavailable reference values.</p>
    <label>Evidence branch<select className="form-input" aria-label="Evidence branch" value={branch} onChange={event=>{setChoice(event.target.value);setSelection(null);}}>{ids.map(id=><option key={id}>{id}</option>)}</select></label>
    <p style={{overflowWrap:'anywhere'}}>CT SHA-256: <code>{value.document.source.source_sha256}</code>. Record: <code>{value.sha256}</code>.</p>
    <svg viewBox="0 0 900 300" role="img" aria-label="Research area profiles and unresolved disagreements" style={{width:'100%',background:'#FDFFFC',border:'1px solid #ddd'}}>
      {rows.filter(row=>row.comparison==='disagreement_unresolved').map(row=><rect key={row.index} x={x(row.s_mm)-3} y="25" width="6" height="225" fill="#f59e0b" opacity=".25"/>)}
      {[selected.left_window_mm,selected.right_window_mm].map((range,i)=>{const [a,b]=clipped(range);return b>=a?<rect key={i} x={x(a)} y="25" width={x(b)-x(a)} height="225" fill="#15803d" opacity=".1"/>:null;})}
      <path d="M50 25V250H850" fill="none" stroke="#222222"/>
      {series.flatMap(([key,label,color])=>evidenceLineSegments(rows,key).map((line,i)=><polyline key={`${key}-${i}`} data-series={label} points={line.map(([a,b])=>`${x(a)},${y(b)}`).join(' ')} stroke={color} strokeWidth="2" strokeDasharray={key.includes('trigger')?'4 3':undefined} fill="none"><title>{label}</title></polyline>))}
      <line x1={x(selected.s_mm)} x2={x(selected.s_mm)} y1="25" y2="250" stroke="#222222" strokeDasharray="2 3"/>
      <text x="50" y="18" fontSize="13">Area (mm²), unverified</text><text x="50" y="275" fontSize="12">{rows[0].s_mm.toFixed(1)}</text><text x="800" y="275" fontSize="12">{rows.at(-1).s_mm.toFixed(1)}</text><text x="330" y="295" fontSize="13">Supplied branch arc length (mm)</text>
      <text x="5" y="250" fontSize="11">0</text><text x="5" y="40" fontSize="11">{top.toFixed(1)}</text>
    </svg>
    <ul>{series.map(([,label,color])=><li key={label}><span style={{color}}>{label}</span></li>)}</ul>
    <p>Orange bands: unresolved section-trigger disagreements. Green bands: selected sample's two reference-support windows. Raw triggers can fail minimum contiguous-region support; region IDs below distinguish those cases. No anatomical proximal/distal direction is assumed.</p>
    <p>Selected sample {selected.index}, s={selected.s_mm.toFixed(3)} mm; native IJK {selected.sample_ijk.map(n=>n.toFixed(3)).join(', ')}; RAS mm {selected.world_ras_mm.map(n=>n.toFixed(3)).join(', ')}.</p>
    <p>Reference windows: [{selected.left_window_mm.map(n=>n.toFixed(3)).join(', ')}] and [{selected.right_window_mm.map(n=>n.toFixed(3)).join(', ')}] mm. Valid reference samples: {selected.reference_samples_each_side.join(' / ')}. Status: {selected.status}; {selected.reason??'no refusal'}.</p>
    <div className="table-wrapper"><table className="data-table"><caption>Underlying source-linked section calculations; unavailable values remain gaps</caption>
      <thead><tr><th>Sample / s (mm)</th><th>Area mm²</th><th>R1 reference / trigger mm²</th><th>R2 reference / trigger mm²</th><th>Raw triggers R1 / R2</th><th>Accepted region IDs</th><th>Status / reason / comparison</th></tr></thead>
      <tbody>{rows.map(row=><tr key={row.index} aria-selected={row.index===selected.index}><td><button type="button" className="btn btn-ghost btn-sm" disabled={busy} onClick={()=>{setSelection(row.index);onLocate(branch,row.index);}}>Locate research sample {row.index}</button><br/>{number(row.s_mm)}</td>
        <td>{number(row.sampled_area_mm2)}</td><td>{number(row.r1_reference_area_mm2)} / {number(row.r1_trigger_area_mm2)}</td><td>{number(row.r2_reference_area_mm2)} / {number(row.r2_trigger_area_mm2)}</td><td>{String(row.r1_raw_trigger)} / {String(row.r2_raw_trigger)}</td><td>{[...row.r1_regions,...row.r2_regions].join(', ')||'None'}</td><td>{row.status}: {row.reason??'no refusal'}; {row.comparison}</td></tr>)}</tbody>
    </table></div>
  </details>;
}
