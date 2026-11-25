import {useEffect, useRef, useState} from 'react';
import AppShell from '../components/AppShell';
import {ErrorState, Loading, PageHeader, Panel} from '../components/ui';
import {useAuth} from '../context/AuthContext';
import {experimentalStenosisApi} from '../api/experimental-stenosis';
import RealVolumeResearchPanel from '../components/RealVolumeResearchPanel.jsx';

const SIZE=24, classes=['normal','mild','moderate','severe','critical_very_severe'];
const initial={sampleId:'1',classId:'2',seed:'1729',thresholds:['10','30','50','70']};

function Raster({values,label,heat=false,markers=[]}) {
  const valid=Array.isArray(values)&&values.length===SIZE*SIZE;
  if(!valid)return <p role="note">Slice unavailable.</p>;
  return <div role="img" aria-label={label} style={{position:'relative',display:'grid',gridTemplateColumns:`repeat(${SIZE}, minmax(0,1fr))`,width:'min(100%, 320px)',aspectRatio:'1',border:'1px solid #aab2a6',background:'#121412'}}>
    {values.map((value,index)=>{const v=Math.max(0,Math.min(1,Number(value)||0));const color=heat?`rgb(${Math.round(255*v)}, ${Math.round(36+130*v)}, ${Math.round(120+110*(1-v))})`:`rgb(${Math.round(255*v)},${Math.round(255*v)},${Math.round(255*v)})`;return <span key={index} aria-hidden="true" style={{backgroundColor:color}}/>;})}
    {markers.map(marker=><span key={marker.id} aria-hidden="true" title={marker.id} style={{position:'absolute',left:`${marker.i/(SIZE-1)*100}%`,top:`${marker.j/(SIZE-1)*100}%`,width:10,height:10,borderRadius:'50%',background:'#f59e0b',border:'2px solid #111',transform:'translate(-50%,-50%)'}}/>)}
  </div>;
}

function areaProfile(result) {
  const metrics=result.geometry_analysis.metrics,values=metrics.area_profile_synthetic_units2,positions=metrics.position_profile_synthetic_units;
  if(!Array.isArray(values)||values.length!==positions.length||!values.length)return null;
  const max=Math.max(...values,1),x=i=>20+i*760/Math.max(1,values.length-1),y=n=>210-n/max*180;
  return <svg viewBox="0 0 800 245" role="img" aria-label="Synthetic geometry area profile and candidate intervals" style={{width:'100%',background:'#fff',border:'1px solid #d9ded6'}}>
    <path d={`M${values.map((v,i)=>`${x(i)},${y(v)}`).join(' L')}`} fill="none" stroke="#256d5a" strokeWidth="3"/>
    {result.geometry_analysis.candidates.map(c=>{const interval=c.location.candidate_extent_synthetic_units,lo=positions.indexOf(Math.min(...positions.filter(p=>p>=interval[0]))),hi=positions.indexOf(Math.max(...positions.filter(p=>p<=interval[1])));return <rect key={c.candidate_id} x={x(Math.max(0,lo))} y="18" width={Math.max(8,x(Math.max(0,hi))-x(Math.max(0,lo)))} height="190" fill="#f59e0b" opacity=".18"><title>{c.candidate_id}: synthetic candidate region</title></rect>;})}
    <path d={`M20 210 H780`} stroke="#303730"/><text x="24" y="235" fontSize="12">Synthetic axial position (voxel units)</text><text x="24" y="15" fontSize="12">Cross-sectional area (voxel units²)</text>
  </svg>;
}

export default function ExperimentalStenosis() {
  const {user}=useAuth();
  const [form,setForm]=useState(initial),[status,setStatus]=useState(null),[sample,setSample]=useState(null),[result,setResult]=useState(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);
  const generation=useRef(0),abort=useRef(null);
  function changeForm(key,value){generation.current++;abort.current?.abort();abort.current=null;setBusy(false);setForm(current=>({...current,[key]:value}));setSample(null);setResult(null);setError('');}
  useEffect(()=>{
    const id=++generation.current,token=localStorage.getItem('vascuai_token'),controller=new AbortController();abort.current=controller;
    setSample(null);setResult(null);setError('');setBusy(false);setStatus(null);
    const check=()=>generation.current===id&&token&&token===localStorage.getItem('vascuai_token');
    experimentalStenosisApi.status({signal:controller.signal}).then(value=>{if(check())setStatus(value);}).catch(failure=>{if(check()&&!controller.signal.aborted)setError(failure.message);});
    const invalidate=()=>{generation.current++;abort.current?.abort();setSample(null);setResult(null);setStatus(null);setBusy(false);setError('Session changed; synthetic analysis was cleared.');};
    window.addEventListener('storage',invalidate);window.addEventListener('vascuai:unauthorized',invalidate);
    return()=>{generation.current++;controller.abort();window.removeEventListener('storage',invalidate);window.removeEventListener('vascuai:unauthorized',invalidate);};
  },[user?.id,user?.role]);

  async function request(action){
    const id=generation.current,token=localStorage.getItem('vascuai_token');
    const baseParams={sample_id:Number(form.sampleId),synthetic_class_id:Number(form.classId),seed:Number(form.seed)};
    const params=action===experimentalStenosisApi.analyze
      ? {...baseParams,provisional_severity_thresholds_percent:form.thresholds.map(Number)}
      : baseParams;
    const controller=new AbortController();abort.current?.abort();abort.current=controller;setBusy(true);setError('');
    if(action===experimentalStenosisApi.sample){setSample(null);setResult(null);}else setResult(null);
    const valid=()=>generation.current===id&&token&&token===localStorage.getItem('vascuai_token')&&!controller.signal.aborted;
    try{const value=await action(params,{signal:controller.signal});if(!valid())return;
      if(action===experimentalStenosisApi.sample){setSample(value);setResult(null);}else setResult(value);
    }catch(failure){if(valid())setError(failure.message||'Synthetic workflow request failed.');}
    finally{if(valid())setBusy(false);}
  }

  function exportResult(){if(!result)return;const blob=new Blob([JSON.stringify(result,null,2)],{type:'application/json'}),url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download=`vascuai-synthetic-stenosis-${result.provenance.synthetic_sample_id}.json`;link.click();URL.revokeObjectURL(url);}
  const k=sample?.middle_slice_k??12;
  const camSlice=result?.explainability?.heatmap_values?Array.from({length:SIZE*SIZE},(_,i)=>result.explainability.heatmap_values[(i*SIZE)+k]):null;
  const probabilities=result?.model?.class_probabilities_uncalibrated??[];
  const best=probabilities.length?Math.max(...probabilities):null;
  const thresholds=form.thresholds.map(Number);
  const thresholdsValid=thresholds.length===4&&thresholds.every(Number.isFinite)&&thresholds[0]>=0&&thresholds[3]<=100&&thresholds.every((value,index)=>index===0||thresholds[index-1]<value);
  return <AppShell>
    <PageHeader eyebrow="EXPERIMENTAL RESEARCH" title="Experimental Stenosis Analysis" description="A separate synthetic phantom workbench. It never accepts patient cases, CT uploads, or clinical records."/>
    <div className="card" role="note"><strong>Synthetic research only — not a diagnosis.</strong><p>All displayed classes, geometric estimates, model probabilities and Grad-CAM are generated from synthetic phantoms. Provisional categories and uncalibrated softmax scores are not clinical measurements or confidence.</p></div>
    {status===null&&!error&&<Loading label="Checking the optional synthetic model checkpoint…"/>}
    {status&&!status.available&&<div role="status" className="notice">Synthetic model inference unavailable: {status.reason||'checkpoint not configured'}. Phantom preview and geometry-only processing remain available; no model output is assumed.</div>}
    {error&&<ErrorState error={error} retry={()=>experimentalStenosisApi.status().then(setStatus).catch(failure=>setError(failure.message))}/>}
    <Panel title="Generate a synthetic vessel" description="The server regenerates a small phantom from these bounded parameters; no volume or patient identifier is accepted.">
      <div className="form-grid">
        <label>Sample ID<input className="form-input" type="number" min="0" max="1000000" value={form.sampleId} onChange={e=>changeForm('sampleId',e.target.value)}/></label>
        <label>Synthetic class<select className="form-input" value={form.classId} onChange={e=>changeForm('classId',e.target.value)}>{classes.map((name,id)=><option key={name} value={id}>{name.replaceAll('_',' ')}</option>)}</select></label>
        <label>Deterministic seed<input className="form-input" type="number" min="0" max="2147483647" value={form.seed} onChange={e=>changeForm('seed',e.target.value)}/></label>
      </div>
      <fieldset><legend>Provisional research category thresholds (%)</legend><p>Configurable software categories only; these boundaries are not clinical cutoffs.</p><div className="form-grid">{form.thresholds.map((value,index)=><label key={index}>Boundary {index+1}<input className="form-input" type="number" min="0" max="100" step="0.1" value={value} onChange={e=>changeForm('thresholds',form.thresholds.map((item,i)=>i===index?e.target.value:item))}/></label>)}</div>{!thresholdsValid&&<p role="alert">Enter four strictly increasing values from 0 to 100.</p>}</fieldset>
      <div className="page-actions"><button className="btn btn-primary" type="button" disabled={busy||!form.sampleId||!form.seed} onClick={()=>request(experimentalStenosisApi.sample)}>Generate phantom</button><button className="btn btn-ghost" type="button" disabled={busy||!sample||!status?.available||!thresholdsValid} onClick={()=>request(experimentalStenosisApi.analyze)}>Run experimental analysis</button>{busy&&<span role="status">Generating and analyzing synthetic data???</span>}</div>
    </Panel>
    {!sample&&!busy&&<p>No synthetic sample selected. No result has been assumed.</p>}
    {sample&&<Panel title={`Synthetic sample ${sample.sample_id}`} description={`${sample.class_label} generator class; shape ${sample.shape.join(' × ')}; synthetic sample SHA-256 ${sample.provenance.volume_sha256}`}>
      <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(240px,1fr))',gap:'1rem'}}><div><h3>Generated central slice</h3><Raster values={sample.middle_slice.flat()} label="Synthetic vessel phantom central slice" markers={result?.geometry_analysis.candidates.filter(c=>c.location.bounding_box_ijk.min[2]<=k&&c.location.bounding_box_ijk.max[2]>=k).map(c=>({id:c.candidate_id,i:c.location.center_ijk[0],j:c.location.center_ijk[1]}))||[]}/>{result?.geometry_analysis.candidates.length>0&&<p>Orange markers indicate synthetic candidate centers that intersect this slice.</p>}</div>{result&&camSlice&&<div><h3>3D CNN Grad-CAM (central slice)</h3><Raster values={camSlice} heat label="Synthetic-only model Grad-CAM central slice"/></div>}</div>
    </Panel>}
    {result&&<>
      <Panel title="Experimental result" description={`Created ${new Date(result.generated_at).toLocaleString()} • model ${result.model.model_id} / ${result.model.model_version} • checkpoint ${result.model.checkpoint_sha256}`}>
        <p><strong>{result.notice}</strong></p>
        <dl><dt>Generated synthetic class</dt><dd>{result.provenance.synthetic_class_label}</dd><dt>3D CNN predicted class</dt><dd>{result.model.predicted_synthetic_class}</dd><dt>Top uncalibrated softmax probability</dt><dd>{(best*100).toFixed(1)}% — not clinical confidence</dd><dt>Geometry candidate count</dt><dd>{result.geometry_analysis.candidate_count} — absence is not a clinical negative</dd><dt>Clinical validation / gate</dt><dd>{String(result.clinical_validation)} / {String(result.clinical_gate_authorized)}</dd></dl>
        <div className="table-wrapper"><table className="data-table"><caption>Synthetic model scores only</caption><thead><tr><th>Class</th><th>Uncalibrated softmax score</th></tr></thead><tbody>{classes.map((name,i)=><tr key={name}><th>{name.replaceAll('_',' ')}</th><td>{(probabilities[i]*100).toFixed(2)}%</td></tr>)}</tbody></table></div>
        <button className="btn btn-ghost" type="button" onClick={exportResult}>Export research JSON</button>
      </Panel>
      <Panel title="Experimental geometry measurements" description="Synthetic voxel-equivalent estimates from area-equivalent cross-sections along the generator-declared axis; not mm, anatomy, or clinical measurements.">
        {areaProfile(result)}
        {result.geometry_analysis.candidates.length===0?<p role="status">No synthetic candidate passed this provisional geometric trigger. This does not indicate absence of disease.</p>:<div className="table-wrapper"><table className="data-table"><caption>Provisional synthetic candidates only</caption><thead><tr><th>Candidate</th><th>Center IJK</th><th>Interval</th><th>Estimated minimum/reference radius</th><th>Estimated narrowing</th><th>Provisional research category</th><th>Availability / confidence</th></tr></thead><tbody>{result.geometry_analysis.candidates.map(c=><tr key={c.candidate_id}><th>{c.candidate_id}</th><td>{c.location.center_ijk.map(n=>n.toFixed(2)).join(', ')}</td><td>{c.location.candidate_extent_synthetic_units.map(n=>n.toFixed(1)).join(' to ')}</td><td>{`${c.measurements.minimum_radius_synthetic_units.toFixed(2)} / ${c.measurements.reference_radius_synthetic_units.toFixed(2)} voxel units`}</td><td>{c.measurements.estimated_percentage_narrowing_synthetic_only==null?'Unavailable':`${c.measurements.estimated_percentage_narrowing_synthetic_only.toFixed(1)}% synthetic only`}</td><td>{c.measurements.severity_synthetic_only||'Unavailable'} (provisional)</td><td>{c.measurements.measurement_availability}; confidence unavailable</td></tr>)}</tbody></table></div>}
        <details><summary>Measurement, localization and explainability provenance</summary><p>Measurement method: {result.geometry_analysis.measurement_provenance.method}. Reference selection: {result.geometry_analysis.metrics.reference_selection}; radial squared quantile {result.geometry_analysis.metrics.radial_squared_quantile}; peak prominence {result.geometry_analysis.metrics.peak_prominence}; trigger ratio {result.geometry_analysis.metrics.trigger_ratio}.</p><p>Severity boundaries: {result.geometry_analysis.measurement_provenance.provisional_severity_thresholds_percent.join(', ')}%. These are configurable provisional research categories, not clinical cutoffs. No calibrated measurement confidence or uncertainty is available.</p><p>Axis source: generator-specified synthetic axis, not an automatically extracted anatomical centerline. Input SHA-256: {result.provenance.volume_sha256}; checkpoint SHA-256: {result.model.checkpoint_sha256}. Grad-CAM is limited to the synthetic CNN.</p><p>No case ID, patient record, clinical gate, or persisted analysis history is present. The JSON export includes estimates, measurement method/configuration and source/checkpoint hashes.</p></details>
        <dl><dt>Estimated reference radius</dt><dd>{result.geometry_analysis.metrics.reference_radius_synthetic_units.toFixed(2)} synthetic voxel units</dd><dt>Estimated minimum profile radius</dt><dd>{result.geometry_analysis.metrics.minimum_radius_synthetic_units.toFixed(2)} synthetic voxel units</dd><dt>Estimated diameter narrowing</dt><dd>{result.geometry_analysis.metrics.estimated_percentage_narrowing_synthetic_only==null?'Unavailable':`${result.geometry_analysis.metrics.estimated_percentage_narrowing_synthetic_only.toFixed(1)}% (synthetic only)`}</dd><dt>Provisional research category</dt><dd>{result.geometry_analysis.metrics.provisional_severity_synthetic_only||'Unavailable'}; boundaries {result.geometry_analysis.metrics.severity_thresholds_percent_synthetic_only.join(' / ')}%</dd><dt>Measurement availability</dt><dd>{result.geometry_analysis.metrics.measurement_availability}</dd><dt>Measurement confidence / uncertainty</dt><dd>Unavailable; not calibrated or estimated</dd></dl>
      </Panel>
    </>}
    <RealVolumeResearchPanel/>
  </AppShell>;
}
