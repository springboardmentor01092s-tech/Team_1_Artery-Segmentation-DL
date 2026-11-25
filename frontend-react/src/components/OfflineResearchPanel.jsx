import {useLayoutEffect,useRef,useState,useEffect} from 'react';
import {useAuth} from '../context/AuthContext';
import {offlineResearchApi} from '../api/offline-research';
import {MAX_OFFLINE_BYTES,parseOfflineEvidence,offlineBinding} from '../api/offline-research-contract';
import {createOfflineResearchAssessment} from '../lib/research-assessment';
import {saveArtifact} from '../lib/segmentation';
import ResearchEvidence from './ResearchEvidence';
import {segmentationApi} from '../api/segmentation';
import {prepareOriginalCt} from '../lib/ct-review-loader';
import {createCtReviewViewer} from '../lib/ct-review-adapter';
import {graphicsCapabilities,releaseViewer} from '../lib/niivue-adapter';
import {navigateExperimentalCandidate} from '../lib/experimental-candidates';

export default function OfflineResearchPanel({result,onClose}){
  const {user}=useAuth();
  return <Workspace key={`${user?.id}:${user?.role}:${offlineBinding(result)}`} result={result} owner={user} onClose={onClose}/>;
}

function Workspace({result,owner,onClose}){
  const [accepted,setAccepted]=useState(null),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const state=useRef({alive:false,generation:0,op:0,controller:null}),viewer=useRef(null);
  useLayoutEffect(()=>{
    const s=state.current;s.alive=true;s.generation++;
    const token=localStorage.getItem('vascuai_token');
    const invalidate=e=>{if(e.type==='storage'&&e.key!==null&&e.key!=='vascuai_token')return;s.generation++;s.controller?.abort();setAccepted(null);setBusy(false);setError('Session changed. Reopen offline research.');};
    window.addEventListener('storage',invalidate);window.addEventListener('vascuai:unauthorized',invalidate);
    const freshness=()=>{if(token!==localStorage.getItem('vascuai_token'))invalidate({type:'session'});};
    const timer=setInterval(freshness,500);window.addEventListener('focus',freshness);
    return()=>{s.alive=false;s.generation++;s.controller?.abort();clearInterval(timer);window.removeEventListener('focus',freshness);window.removeEventListener('storage',invalidate);window.removeEventListener('vascuai:unauthorized',invalidate);};
  },[owner]);
  useEffect(()=>{
    if(!accepted||busy)return;
    const controller=new AbortController(),generation=state.current.generation,token=localStorage.getItem('vascuai_token');let pending=false;
    const fresh=async()=>{
      if(pending||controller.signal.aborted)return;pending=true;
      try{
        const value=await offlineResearchApi.identity(result,{signal:controller.signal});
        if(value.mask_file_sha256!==accepted.receipt.source_files.mask_file_sha256)throw new Error('Stored research mask changed.');
      }catch{
        if(!controller.signal.aborted&&state.current.alive&&generation===state.current.generation&&token===localStorage.getItem('vascuai_token')){
          state.current.generation++;state.current.controller?.abort();setAccepted(null);setError('Research source identity or access could not be verified. Reload evidence; no stale result is retained.');
        }
      }finally{pending=false;}
    };
    window.addEventListener('focus',fresh);const timer=setInterval(fresh,60000);
    return()=>{controller.abort();clearInterval(timer);window.removeEventListener('focus',fresh);};
  },[accepted,busy,result]);
  async function perform(action){
    const s=state.current;s.controller?.abort();const controller=new AbortController();s.controller=controller;
    const op=++s.op,generation=s.generation,token=localStorage.getItem('vascuai_token');
    const current=()=>s.alive&&s.op===op&&s.generation===generation&&!controller.signal.aborted&&token===localStorage.getItem('vascuai_token');
    const check=()=>{if(!current()||!token||!owner)throw new Error('Session/source changed; no offline evidence accepted.');};
    setBusy(true);setError('');
    try{check();await action(check,controller.signal);}catch(failure){if(s.alive&&s.op===op){setAccepted(null);setError(failure.message);}}
    finally{if(s.alive&&s.op===op)setBusy(false);}
  }
  async function verify(text,check,signal){
    const receipt=await offlineResearchApi.verify(result,text,{signal});check();
    const assessment=await createOfflineResearchAssessment(receipt,result);check();return {receipt,assessment,text};
  }
  function load(event){
    const file=event.target.files?.[0];event.target.value='';setAccepted(null);if(!file)return;
    return perform(async(check,signal)=>{
      if(!file.size||file.size>MAX_OFFLINE_BYTES)throw new Error('Offline JSON must be nonempty and at most 2 MiB.');
      const text=await file.text();check();const value=JSON.parse(text);
      let evidence=text,expected=null;
      if(value.schema_version==='offline-research-workspace/0.1'){
        if(Object.keys(value).sort().join(',')!=='assessment_sha256,clinical_gate_authorized,evidence_text,procedure_version,schema_version,training_release_authorized'
          ||value.procedure_version!=='0.1'||value.clinical_gate_authorized!==false||value.training_release_authorized!==false)throw new Error('Invalid read-only research workspace.');
        evidence=value.evidence_text;expected=value.assessment_sha256;
      }
      parseOfflineEvidence(evidence);const next=await verify(evidence,check,signal);
      if(expected!==null&&expected!==next.assessment.sha256)throw new Error('Restored assessment hash/procedure/source mismatch.');
      check();setAccepted(next);
    });
  }
  const download=()=>perform(async(check,signal)=>{
    const next=await verify(accepted.text,check,signal);
    if(next.assessment.sha256!==accepted.assessment.sha256)throw new Error('Research calculation changed; reload evidence.');
    const text=JSON.stringify({schema_version:'offline-research-workspace/0.1',procedure_version:'0.1',evidence_text:accepted.text,
      assessment_sha256:next.assessment.sha256,clinical_gate_authorized:false,training_release_authorized:false},null,2);
    if(new TextEncoder().encode(text).length>MAX_OFFLINE_BYTES)throw new Error('Read-only export exceeds 2 MiB; nothing exported.');
    check();saveArtifact({blob:new Blob([text],{type:'application/json;charset=utf-8'}),filename:`vascuai-case-${result.case_id}-offline-research.json`});
  });
  const locate=(branch,index)=>perform(async(check,signal)=>{
    const next=await verify(accepted.text,check,signal);
    if(next.assessment.sha256!==accepted.assessment.sha256)throw new Error('Research calculation/source changed; reload evidence.');
    const row=next.receipt.profile.branches.find(b=>b.branch_id===branch)?.sections[index];
    if(!row||!viewer.current)throw new Error('CT navigation unavailable. Use these original IJK/RAS coordinates in a verified desktop viewer.');
    check();navigateExperimentalCandidate(viewer.current,row);
  });
  return <section className="card stack no-print" aria-label="Offline research workbench" style={{padding:'1rem'}}>
    <div className="page-actions"><h2>Offline-generated provisional research evidence</h2><button className="btn btn-ghost" onClick={onClose}>Close offline research</button></div>
    <p className="notice">Read-only research; not expert annotation or a clinical diagnosis. Both release authorizations remain false. Stored files and the declared implementation are rechecked by the authenticated server; local checksums are not clinical attestations.</p>
    <p>This path downloads original CT only for optional navigation. The complete mask stays on the server. Existing mask-preview and CT display budgets are unchanged.</p>
    <label>Offline evidence or read-only workspace JSON<input aria-label="Offline evidence JSON" type="file" accept=".json,application/json" disabled={busy} onChange={load}/></label>
    {busy&&<p role="status">Recomputing and verifying offline evidence against stored sources…</p>}
    {error&&<p role="alert" className="notice error">{error}</p>}
    {!accepted&&!busy&&<p>No offline evidence accepted.</p>}
    {accepted&&<>
      <p>CT SHA-256: <code style={{overflowWrap:'anywhere'}}>{accepted.receipt.profile.source.source_sha256}</code>. Canonical mask identity: <code style={{overflowWrap:'anywhere'}}>{accepted.receipt.profile.source.mask_sha256}</code>.</p>
      <p>Implementation: <code>{accepted.receipt.implementation_sha256.sampler}</code>. Procedure version: 0.1. Source run: {result.id}.</p>
      <p>R1: {accepted.assessment.document.records[0].record.evidence.reduce((n,b)=>n+b.proposals.length,0)} provisional regions. R2: {accepted.assessment.document.records[1].record.evidence.reduce((n,b)=>n+b.proposals.length,0)} provisional regions. R3 preserves disagreements; confidence, clinical severity and stenosis attribution are unavailable.</p>
      <button className="btn btn-ghost" disabled={busy} onClick={download}>Export read-only offline workspace</button>
      <OfflineCt key={accepted.receipt.evidence_sha256} result={result} receipt={accepted.receipt} viewerRef={viewer}/>
      <ResearchEvidence value={accepted.assessment} busy={busy} onLocate={locate}/>
    </>}
  </section>;
}

function OfflineCt({result,receipt,viewerRef}){
  const canvas=useRef(null),[ready,setReady]=useState(false),[error,setError]=useState(''),[location,setLocation]=useState(null);
  const [width,setWidth]=useState(1000),[level,setLevel]=useState(300);
  useEffect(()=>{
    const controller=new AbortController(),token=localStorage.getItem('vascuai_token');let alive=true,instance;
    const current=()=>{if(!alive||controller.signal.aborted||token!==localStorage.getItem('vascuai_token'))throw new Error('CT session changed.');};
    (async()=>{try{
      graphicsCapabilities(receipt.profile.geometry.shape);current();
      const bytes=await segmentationApi.loadVolume(result.case_id,result.id,'source',{signal:controller.signal});current();
      const source={case_id:result.case_id,source_sha256:receipt.profile.source.source_sha256,shape:receipt.profile.geometry.shape,affine:receipt.profile.geometry.affine,units:'mm'};
      const packet=await prepareOriginalCt(bytes,source,{signal:controller.signal});current();
      instance=await createCtReviewViewer(canvas.current,packet,value=>{if(alive)setLocation(value);},controller.signal);current();viewerRef.current=instance;setReady(true);
    }catch(failure){if(alive){releaseViewer(instance);viewerRef.current=null;setReady(false);setError(failure.message);}}})();
    return()=>{alive=false;controller.abort();viewerRef.current=null;releaseViewer(instance);};
  },[result,receipt,viewerRef]);
  function windowing(w,l){setWidth(w);setLevel(l);const v=viewerRef.current;if(!v)return;v.volumes[0].cal_min=l-w/2;v.volumes[0].cal_max=l+w/2;v.updateGLVolume();v.drawScene();}
  return <section aria-label="Research original CT only"><h3>Original CT navigation — no mask download</h3>
    {error&&<p className="notice" role="status">CT display unavailable: {error}. Verified profiles remain readable; use original IJK/RAS in a desktop viewer. No unsupported image is substituted.</p>}
    <div className="volume-canvas-container"><canvas ref={canvas} role="img" aria-label="Research original CT without segmentation" style={{visibility:ready?'visible':'hidden'}}/></div>
    {ready&&<><p role="status">Verified original CT · one volume · no segmentation overlay.</p>
      <label>Research CT window width<input aria-label="Research CT window width" type="range" min="1" max="3000" value={width} onChange={e=>windowing(Number(e.target.value),level)}/></label>
      <label>Research CT window level<input aria-label="Research CT window level" type="range" min="-1000" max="1500" value={level} onChange={e=>windowing(width,Number(e.target.value))}/></label>
      {location&&<p>Offline CT crosshair RAS: {location.world.map(n=>n.toFixed(2)).join(', ')} mm. Native IJK: {location.native?.join(', ')??'outside CT'}.</p>}</>}
  </section>;
}
