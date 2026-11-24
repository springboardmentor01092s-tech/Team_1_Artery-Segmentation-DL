// Derived visual evidence only. Input is the current validated research snapshot;
// standalone files must first pass validateResearchAssessment at the boundary.
export function researchEvidenceRows(value,branchId) {
  const doc=value.document,profile=doc.profile.branches.find(b=>b.branch_id===branchId);
  const branches=doc.records.map(item=>item.record.evidence.find(b=>b.branch_id===branchId));
  if(!profile || branches.some(b=>!b) || branches.some(b=>b.sections.length!==profile.sections.length))throw new Error('Research evidence branch mismatch.');
  const p=doc.profile.parameters;
  return profile.sections.map((row,i)=>{
    const [r1,r2,r3]=branches.map(branch=>branch.sections[i]);
    if([r1,r2,r3].some(r=>r.s_mm!==row.s_mm))throw new Error('Research sampling order mismatch.');
    const membership=branches.slice(0,2).map(branch=>branch.proposals.filter(proposal=>row.s_mm>=proposal.interval_s_mm[0]&&row.s_mm<=proposal.interval_s_mm[1]).map(proposal=>proposal.proposal_id));
    return {index:i,s_mm:row.s_mm,sample_ijk:[...row.sample_ijk],world_ras_mm:[...row.world_ras_mm],
      sampled_area_mm2:row.diagnostic_area_mm2,status:row.status,reason:row.reason,
      left_window_mm:[row.s_mm-p.reference_outer_mm,row.s_mm-p.reference_inner_mm],
      right_window_mm:[row.s_mm+p.reference_inner_mm,row.s_mm+p.reference_outer_mm],
      reference_samples_each_side:[...row.reference_samples_each_side],
      r1_reference_area_mm2:r1.reference_area_mm2,r2_reference_area_mm2:r2.reference_area_mm2,
      r1_trigger_area_mm2:r1.reference_area_mm2===null?null:r1.reference_area_mm2*p.area_ratio_trigger,
      r2_trigger_area_mm2:r2.reference_area_mm2===null?null:r2.reference_area_mm2*p.area_ratio_trigger,
      r1_raw_trigger:r1.proposed,r2_raw_trigger:r2.proposed,r1_regions:membership[0],r2_regions:membership[1],comparison:r3.status};
  });
}

export function evidenceLineSegments(rows,key) {
  const lines=[];let current=[];
  for(const row of rows) {
    if(row[key]===null){if(current.length)lines.push(current);current=[];}
    else if(!Number.isFinite(row[key]) || row[key]<0)throw new Error('Invalid profile evidence value.');
    else current.push([row.s_mm,row[key]]);
  }
  if(current.length)lines.push(current);
  return lines;
}
