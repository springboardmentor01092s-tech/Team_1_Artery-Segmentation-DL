import {lazy,Suspense,useEffect,useRef,useState} from 'react';
import {Save,ShieldCheck} from 'lucide-react';
import AppShell from '../components/AppShell';
import {PageHeader,Panel,ErrorState} from '../components/ui';
import {useAuth} from '../context/AuthContext';
import {adjudicationsApi as api,canonical} from '../api/review-adjudications';
import {reviewCoverage} from '../lib/review-coverage';
const AdjudicationCtViewer=lazy(()=>import('../components/AdjudicationCtViewer'));

export default function ReviewAdjudications(){
  const {user}=useAuth();
  return <AppShell breadcrumbs={[{label:'Third-reader adjudication'}]}><PageHeader title="Third-reader adjudication" eyebrow="Unverified human research review"
    description="Both independent reviews remain frozen. Adjudication is not clinical approval or permission to train."/>
    {user&&<Workspace key={`${user.id}:${user.role}`} user={user}/>}</AppShell>;
}
function Workspace({user}){
  const [items,setItems]=useState([]),[catalogue,setCatalogue]=useState(null),[selected,setSelected]=useState(''),[item,setItem]=useState(null);
  const [doc,setDoc]=useState(null),[saved,setSaved]=useState(null),[busy,setBusy]=useState(true),[error,setError]=useState(''),[message,setMessage]=useState('');
  const [studyId,setStudyId]=useState(''),[credentialId,setCredentialId]=useState(''),[conflict,setConflict]=useState(false),[ack,setAck]=useState(false);
  const [revisionLookup,setRevisionLookup]=useState('1'),[historical,setHistorical]=useState(null);
  const [ctOpen,setCtOpen]=useState(false);
  const operation=useRef({generation:0,controller:null});
  const begin=()=>{
    operation.current.controller?.abort();const controller=new AbortController(),generation=++operation.current.generation,token=localStorage.getItem('vascuai_token');
    operation.current.controller=controller;setBusy(true);setError('');setMessage('');
    return {signal:controller.signal,current:()=>!controller.signal.aborted&&generation===operation.current.generation&&token===localStorage.getItem('vascuai_token')};
  };
  const fail=(task,e)=>{if(task.current()){setError(e.message||'Adjudication request failed');setBusy(false);}};
  useEffect(()=>{
    const state=operation.current,task=begin();
    (async()=>{try{
      if(user.role==='Admin'){const data=await api.catalogue(task);if(task.current())setCatalogue(data);}
      else {const data=await api.list(task);if(task.current())setItems(data.items);}
      if(task.current())setBusy(false);
    }catch(e){fail(task,e);}})();
    return()=>{state.generation++;state.controller?.abort();};
    // Account changes remount the workspace. No review is stored in localStorage.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  },[]);
  useEffect(()=>{
    const token=localStorage.getItem('vascuai_token');let alive=true;
    const check=()=>{
      if(!alive||token===localStorage.getItem('vascuai_token'))return;
      operation.current.generation++;operation.current.controller?.abort();
      setCtOpen(false);setItem(null);setDoc(null);setSaved(null);setHistorical(null);setCatalogue(null);setItems([]);setBusy(false);
      setError('Your session changed. Sign in again before reopening private adjudication evidence.');
    };
    window.addEventListener('storage',check);window.addEventListener('vascuai:unauthorized',check);const timer=setInterval(check,500);
    return()=>{alive=false;clearInterval(timer);window.removeEventListener('storage',check);window.removeEventListener('vascuai:unauthorized',check);};
  },[]);
  const load=async()=>{
    setCtOpen(false);
    const task=begin();try{
      const value=await api.detail(selected,user.id,task);if(!task.current())return;
      setItem(value);setSaved(value.current);setHistorical(null);setDoc(value.current?.record.document||{
        schema_version:'review-adjudication/0.1',assignment_id:value.id,source_sha256:value.source.source_sha256,protocol_version:value.protocol_version,
        r1_submission_sha256:value.parents[0].record_sha256,r2_submission_sha256:value.parents[1].record_sha256,
        outcome:'not_assessed',reason:'Not assessed; manual third-reader review required.',correspondences:[],resolutions:[],clinical_gate_authorized:false,training_release_authorized:false});
      setConflict(false);setAck(false);setBusy(false);
    }catch(e){fail(task,e);}
  };
  const save=async()=>{
    const task=begin();try{const value=await api.save(item,user.id,doc,saved?.record.revision||0,task);if(!task.current())return;
      setSaved(value);setDoc(value.record.document);setBusy(false);setMessage(`Unverified adjudication saved at revision ${value.record.revision}.`);
    }catch(e){if(task.current()&&!e.localValidation&&! [400,401,403,404,413,422].includes(e.response?.status))setConflict(true);fail(task,e);}
  };
  const submit=async()=>{
    const task=begin();try{const value=await api.submit(item,user.id,saved,task);if(!task.current())return;
      setSaved(value);setBusy(false);setMessage('Adjudication frozen as unverified. Clinical and training release remain disabled.');
    }catch(e){if(task.current()&&! [400,401,403,404,413,422].includes(e.response?.status))setConflict(true);fail(task,e);}
  };
  const frozen=saved?.record.status==='adjudicated_unverified',disabled=busy||conflict||frozen||!item?.source_current;
  const patch=(key,value)=>setDoc(current=>({...current,[key]:value}));
  const add=()=>{const id=crypto.randomUUID();setDoc(current=>({...current,correspondences:[...current.correspondences,{id,r1_lesion_ids:[],r2_lesion_ids:[],relation:'uncertain',reason:''}],
    resolutions:[...current.resolutions,{correspondence_id:id,field:'lesion_presence',decision:'unresolved',reason:''}]}));};
  const rowPatch=(collection,index,key,value)=>setDoc(current=>({...current,[collection]:current[collection].map((row,i)=>i===index?{...row,[key]:value}:row)}));
  return <>
    <div className="notice" role="note"><ShieldCheck size={20}/><p>clinical_gate_authorized=false; training_release_authorized=false. Human annotations and decisions remain unverified.</p></div>
    {error&&<ErrorState error={error}/>}<p role="status">{message}</p>
    {catalogue&&<Panel title="Coordinator: assign a third reviewer" description="No findings are exposed to the coordinator. Credential evidence requires separate human verification; there is no self-certification endpoint.">
      {!catalogue.credentials.length&&<p>No verified reviewer credentials are registered. Third-reviewer assignment is blocked until a qualified reviewer and separately approved evidence are available.</p>}
      <label>Review study<select aria-label="Adjudication study" className="form-select" value={studyId} onChange={e=>setStudyId(e.target.value)} disabled={busy}>
        <option value="">Select study</option>{catalogue.studies.map(s=><option key={s.id} value={s.id}>Case {s.case_id} · {s.protocol_version}</option>)}</select></label>
      <label>Verified third reviewer<select aria-label="Verified third reviewer" className="form-select" value={credentialId} onChange={e=>setCredentialId(e.target.value)} disabled={busy}>
        <option value="">Select separately verified credentials</option>{catalogue.credentials.map(c=><option key={c.id} value={c.id}>{c.name} · account {c.reviewer_id}</option>)}</select></label>
      <button className="btn btn-primary" disabled={busy||!studyId||!credentialId} onClick={async()=>{
        const task=begin();try{await api.assign(catalogue.studies.find(s=>s.id===studyId),catalogue.credentials.find(c=>c.id===credentialId),task);
          if(task.current()){setBusy(false);setMessage('Third reviewer assigned. Independent findings remain private to the adjudicator.');}}
        catch(e){fail(task,e);}}}>Assign after both reviews are frozen</button>
    </Panel>}
    {user.role!=='Admin'&&<Panel title="My adjudication assignments" description="Only your assignments are listed; an active credential is checked on every read and write.">
      {!items.length&&<p>No adjudication assignments are available.</p>}
      <label>Assignment<select aria-label="Adjudication assignment" className="form-select" value={selected} onChange={e=>{
        operation.current.generation++;operation.current.controller?.abort();setBusy(false);setSelected(e.target.value);setItem(null);setDoc(null);setSaved(null);setConflict(false);setError('');setCtOpen(false);}}
        ><option value="">Select assignment</option>{items.map(v=><option key={v.id} value={v.id}>Case {v.case_id} · {v.protocol_version}</option>)}</select></label>
      <button className="btn btn-ghost" disabled={busy||!selected} onClick={load}>{conflict?'Reload latest and replace my unsaved adjudication':'Load selected adjudication'}</button>
      {conflict&&<p role="alert">A stale revision or uncertain response blocked saving. Copy your unsaved notes privately, then explicitly reload. No silent overwrite occurs.</p>}
    </Panel>}
    {item&&doc&&<>
      {!item.source_current&&<p role="alert">Original CT changed or is unavailable. Saving and finalization are blocked.</p>}
      <Panel title="Frozen independent reviews" description="R1/R2 identifiers here are roles. Original submission records and their hashes are preserved.">
        <p style={{overflowWrap:'anywhere'}}>Original CT SHA-256: {item.source.source_sha256}</p>
        <button className="btn btn-ghost" disabled={busy||!item.source_current||ctOpen} onClick={()=>setCtOpen(true)}>Open adjudication original CT viewer</button>
        <button className="btn btn-ghost" disabled={busy||!item.source_current} onClick={async()=>{
          const task=begin();try{const value=await api.download(item,user.id,task);if(!task.current())return;
            const url=URL.createObjectURL(value.blob),a=document.createElement('a');a.href=url;a.download=value.filename;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
            setBusy(false);setMessage('Original CT checksum verified. Use an approved local CT viewer; no prediction or overlay is supplied.');
          }catch(e){fail(task,e);}}}>Download verified original CT for adjudication</button>
        {item.parents.map((parent,i)=><details key={parent.record_sha256}><summary>R{i+1} frozen review</summary><p style={{overflowWrap:'anywhere'}}>Record SHA-256: {parent.record_sha256}</p>
          <pre style={{whiteSpace:'pre-wrap'}}>{JSON.stringify(parent.submission.document,null,2)}</pre></details>)}
        <details><summary>Protocol and documentation coverage</summary>
          <p>Protocol: {item.protocol_version}. Counts describe recorded fields, not anatomical coverage, correctness or qualification.</p>
          {reviewCoverage(item).readers.map(row=><p key={row.slot}>{row.slot}: {row.case_disposition}; {row.recorded_lesion_rows} lesion rows recorded; {row.landmarks_recorded} / {row.landmark_fields} landmark fields recorded; {row.manual_diameters_recorded} manual diameter fields recorded.</p>)}
          <p>External packet not bound. Evidence-file receipts and protocol sign-off not verified. Real reviewer qualification and independence are not established.</p>
        </details>
      </Panel>
      {ctOpen&&<Suspense fallback={<p role="status">Loading original CT viewer…</p>}><AdjudicationCtViewer key={`${item.id}:${item.source.source_sha256}`} assignment={item} ownerId={user.id} onClose={()=>setCtOpen(false)}/></Suspense>}
      <Panel title="Immutable adjudication history" description="The latest 50 chain entries are loaded. Every older revision remains individually retrievable.">
        {item.history.length===0?<p>No adjudication version was present at the last reload.</p>:<ol>{item.history.map(row=><li key={row.revision} style={{overflowWrap:'anywhere'}}>Revision {row.revision} · {row.final?'final unverified':'draft unverified'} · {row.record_sha256}</li>)}</ol>}
        <label>Historical revision<input className="form-input" aria-label="Historical revision" type="number" min="1" max={saved?.record.revision||1} value={revisionLookup} onChange={e=>setRevisionLookup(e.target.value)}/></label>
        <button className="btn btn-ghost" disabled={busy||!saved||!Number.isSafeInteger(Number(revisionLookup))||Number(revisionLookup)<1||Number(revisionLookup)>saved.record.revision} onClick={async()=>{
          const task=begin();try{const value=await api.version(item,user.id,Number(revisionLookup),task);if(!task.current())return;setHistorical(value);setBusy(false);}
          catch(e){fail(task,e);}}}>Read immutable historical revision</button>
        {historical&&<pre style={{whiteSpace:'pre-wrap'}}>{JSON.stringify(historical,null,2)}</pre>}
      </Panel>
      <Panel title="Manual correspondence and discrepancy resolution" description="Decisions refer to the original reviews; no consolidated clinical label or percentage is calculated.">
        <fieldset disabled={disabled}><legend>Unverified adjudication worksheet</legend>
          <label>Outcome<select aria-label="Outcome" className="form-select" value={doc.outcome} onChange={e=>patch('outcome',e.target.value)}>{['not_assessed','agreement','resolved_disagreement','unresolved'].map(v=><option key={v}>{v}</option>)}</select></label>
          <label>Decision or unresolved reason<textarea aria-label="Decision or unresolved reason" className="form-input" value={doc.reason} maxLength={2000} onChange={e=>patch('reason',e.target.value)}/></label>
          {doc.correspondences.map((row,index)=><fieldset key={row.id}><legend>Correspondence {index+1}</legend>
            {[0,1].map(i=><label key={i}>R{i+1} lesion references<select multiple className="form-select" aria-label={`Correspondence ${index+1} R${i+1} lesions`} value={row[`r${i+1}_lesion_ids`]}
              onChange={e=>rowPatch('correspondences',index,`r${i+1}_lesion_ids`,Array.from(e.target.selectedOptions,o=>o.value))}>
              {item.parents[i].submission.document.lesions.map(lesion=><option key={lesion.draft_id} value={lesion.draft_id}>{lesion.artery||'Unspecified artery'} · {lesion.segment||'Unspecified segment'} · {lesion.draft_id}</option>)}</select></label>)}
            <label>Relationship<select aria-label="Relationship" className="form-select" value={row.relation} onChange={e=>rowPatch('correspondences',index,'relation',e.target.value)}>{['matched','only_r1','only_r2','uncertain'].map(v=><option key={v}>{v}</option>)}</select></label>
            <label>Correspondence evidence<textarea aria-label="Correspondence evidence" className="form-input" maxLength={2000} value={row.reason} onChange={e=>rowPatch('correspondences',index,'reason',e.target.value)}/></label>
            <button className="btn btn-ghost" disabled={disabled||doc.resolutions.filter(v=>v.correspondence_id===row.id).length>=6} onClick={()=>{
              const used=new Set(doc.resolutions.filter(v=>v.correspondence_id===row.id).map(v=>v.field));
              const field=['lesion_presence','artery_segment','location_boundaries','minimum_diameter','reference_diameter','measurement_method'].find(v=>!used.has(v));
              if(field)setDoc(current=>({...current,resolutions:[...current.resolutions,{correspondence_id:row.id,field,decision:'unresolved',reason:''}]}));
            }}>Add another field decision for correspondence {index+1}</button>
            <button className="btn btn-ghost" onClick={()=>setDoc(current=>({...current,correspondences:current.correspondences.filter(v=>v.id!==row.id),resolutions:current.resolutions.filter(v=>v.correspondence_id!==row.id)}))}>Remove correspondence</button>
          </fieldset>)}
          <button className="btn btn-ghost" onClick={add} disabled={doc.correspondences.length>=200||disabled}>Add manual correspondence</button>
          {doc.resolutions.map((row,index)=><fieldset key={`${row.correspondence_id}:${index}`}><legend>Discrepancy decision {index+1}</legend>
            <label>Field<select aria-label="Field" className="form-select" value={row.field} onChange={e=>rowPatch('resolutions',index,'field',e.target.value)}>{['lesion_presence','artery_segment','location_boundaries','minimum_diameter','reference_diameter','measurement_method'].map(v=><option key={v}>{v}</option>)}</select></label>
            <label>Decision<select aria-label="Decision" className="form-select" value={row.decision} onChange={e=>rowPatch('resolutions',index,'decision',e.target.value)}>{['agreement','prefer_r1','prefer_r2','unresolved'].map(v=><option key={v}>{v}</option>)}</select></label>
            <label>Decision evidence<textarea aria-label="Decision evidence" className="form-input" maxLength={2000} value={row.reason} onChange={e=>rowPatch('resolutions',index,'reason',e.target.value)}/></label>
          </fieldset>)}
        </fieldset>
        <button className="btn btn-primary" disabled={disabled} onClick={save}><Save size={16}/>Save adjudication revision</button>
        {saved&&<p style={{overflowWrap:'anywhere'}}>Saved revision {saved.record.revision} · record SHA-256 {saved.record_sha256}</p>}
        <label><input type="checkbox" checked={ack} onChange={e=>setAck(e.target.checked)} disabled={disabled}/>I reviewed the frozen source-bound records. This submission remains unverified and grants no clinical or training release.</label>
        <button className="btn btn-primary" disabled={disabled||!ack||!saved||canonical(doc)!==canonical(saved.record.document)} onClick={submit}>Freeze unverified adjudication</button>
        {frozen&&<p role="status">Immutable adjudication recorded. Amendments require a separately versioned process; original reviews are retained.</p>}
      </Panel>
    </>}
  </>;
}
