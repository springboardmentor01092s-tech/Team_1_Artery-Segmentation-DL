import {lazy,Suspense,useEffect,useRef,useState} from 'react';
import {Download,Save,RefreshCw,ShieldCheck} from 'lucide-react';
import AppShell from '../components/AppShell';
import {PageHeader,Panel,ErrorState} from '../components/ui';
import {useAuth} from '../context/AuthContext';
import api from '../api/client';
import {reviewAssignmentsApi as reviews} from '../api/review-assignments';
const BlindedCtViewer=lazy(()=>import('../components/BlindedCtViewer'));

export default function ReviewAssignments(){
  const {user}=useAuth();
  return <AppShell breadcrumbs={[{label:'Assigned CT review'}]}>
    <PageHeader eyebrow="Unverified reader preparation" title="Assigned CT review"
      description="Original CT only. Separate account-private R1/R2 preparation; no clinical or training release."/>
    {user&&<Workspace key={`${user.id}:${user.role}`} user={user}/>}
  </AppShell>;
}
function Workspace({user}){
  const [viewerOpen,setViewerOpen]=useState(false);const viewerButton=useRef(null),restoreViewerFocus=useRef(false);
  useEffect(()=>{
    if(!viewerOpen&&restoreViewerFocus.current){restoreViewerFocus.current=false;viewerButton.current?.focus();}
  },[viewerOpen]);
  const [items,setItems]=useState([]),[selected,setSelected]=useState(''),[detail,setDetail]=useState(null),[saved,setSaved]=useState(null);
  const [notes,setNotes]=useState(''),[error,setError]=useState(''),[message,setMessage]=useState(''),[busy,setBusy]=useState(false),[conflict,setConflict]=useState(false);
  const [cases,setCases]=useState([]),[readers,setReaders]=useState([]),[caseId,setCaseId]=useState(''),[preview,setPreview]=useState(null);
  const [r1,setR1]=useState(''),[r2,setR2]=useState(''),[protocol,setProtocol]=useState(''),[ack,setAck]=useState(false),[created,setCreated]=useState(null);
  const operation=useRef({generation:0,controller:null});
  const begin=()=>{
    operation.current.controller?.abort();const controller=new AbortController(),generation=++operation.current.generation;
    operation.current.controller=controller;const token=localStorage.getItem('vascuai_token');
    setBusy(true);setError('');setMessage('');
    return {signal:controller.signal,current:()=>!controller.signal.aborted&&generation===operation.current.generation&&token===localStorage.getItem('vascuai_token')};
  };
  const failed=(task,e)=>{if(task.current()){setError(e.message||'Request failed.');setBusy(false);}};
  const refresh=async()=>{
    const task=begin();
    try{
      const list=await reviews.list(user.id,task);
      if(!task.current())return;setItems(list.items);
      setMessage(list.next_offset===null?'Only your assignments are listed.':'First 50 assignments shown; further assignments require API pagination.');
      if(user.role==='Admin'){
        const [c,u]=await Promise.all([api.get('/cases',{signal:task.signal}),api.get('/admin/users',{signal:task.signal,params:{limit:500,offset:0}})]);
        if(!task.current())return;
        if(!Array.isArray(c.data)||!Array.isArray(u.data))throw new Error('Coordinator catalogue could not be verified.');
        setCases(c.data);setReaders(u.data.filter(v=>v.role==='Clinician'&&v.is_active));
      }
      if(task.current())setBusy(false);
    }catch(e){failed(task,e);}
  };
  useEffect(()=>{
    const state=operation.current;
    refresh();
    return ()=>{state.generation++;state.controller?.abort();};
    // Account changes remount this private workspace; no notes enter browser storage.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  },[]);
  const load=async(item)=>{
    setViewerOpen(false);const task=begin();
    try{
      const [next,document]=await Promise.all([reviews.detail(item,user.id,task),reviews.note(item,user.id,task)]);
      if(!task.current())return;
      setDetail(next);setSaved(document);setNotes(document.notes);setConflict(false);setBusy(false);
      setMessage('Your server draft was loaded. Clinical values remain unverified.');
    }catch(e){failed(task,e);}
  };
  const select=event=>{
    setViewerOpen(false);
    operation.current.generation++;operation.current.controller?.abort();setBusy(false);setSelected(event.target.value);
    setDetail(null);setSaved(null);setNotes('');setConflict(false);setError('');setMessage('');
  };
  const save=async()=>{
    const task=begin();
    try{
      const next=await reviews.save(detail,user.id,notes,saved.revision,task);
      if(!task.current())return;setSaved(next);setBusy(false);setMessage(`Private draft saved at revision ${next.revision}. It is not a submission or expert ground truth.`);
    }catch(e){if(task.current())setConflict(true);failed(task,e);}
  };
  const download=async()=>{
    const task=begin();
    try{
      const result=await reviews.download(detail,task);if(!task.current())return;
      const url=URL.createObjectURL(result.blob),a=document.createElement('a');a.href=url;a.download=result.filename;
      document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
      setBusy(false);setMessage('Original CT checksum verified before download. Use an approved local CT viewer; no AI mask is supplied.');
    }catch(e){failed(task,e);}
  };
  const inspect=async()=>{
    const task=begin();setPreview(null);setCreated(null);
    try{const value=await reviews.preview(Number(caseId),task);if(!task.current())return;setPreview(value);setBusy(false);}catch(e){failed(task,e);}
  };
  const assign=async(event)=>{
    event.preventDefault();const task=begin();setCreated(null);
    try{
      const value=await reviews.assign({case_id:Number(caseId),r1_user_id:Number(r1),r2_user_id:Number(r2),
        expected_ct_sha256:preview.source.source_sha256,protocol_version:protocol,acknowledge_unverified:ack},task);
      if(!task.current())return;setCreated(value);setBusy(false);setPreview(null);setAck(false);
      setMessage('R1/R2 account restrictions are active. No findings are returned to the coordinator.');
    }catch(e){failed(task,e);}
  };
  const currentItem=items.find(item=>item.id===selected);
  return <>
    <div className="notice" role="note"><ShieldCheck size={20}/><p>Clinical gate authorized: false. Training release authorized: false.
      Account separation does not verify clinical qualifications or independence. Formal submissions remain unverified; quantitative stenosis output is unavailable.</p></div>
    {error&&<ErrorState error={error}/>}{message&&<p role="status">{message}</p>}
    <Panel title="My original-CT assignments" description="No other reader’s identity, draft or progress is exposed here.">
      <button className="btn btn-ghost" disabled={busy} onClick={refresh}><RefreshCw size={16}/>Refresh my assignments</button>
      {!items.length&&<p>No original-CT assignments are available for your account.</p>}
      <label>Assignment<select className="form-select" aria-label="Assignment" value={selected} onChange={select}>
        <option value="">Select your assignment</option>{items.map(item=><option key={item.id} value={item.id}>Case {item.case_id} · {item.slot} · {item.protocol_version}</option>)}
      </select></label>
      <button className="btn btn-ghost" disabled={busy||!currentItem} onClick={()=>load(currentItem)}>Load selected assignment</button>
      {detail&&saved&&<>
        <p>Case {detail.case_id} · {detail.slot} · protocol {detail.protocol_version}</p>
        <p style={{overflowWrap:'anywhere'}}>Original CT SHA-256: {detail.source.source_sha256}</p>
        <p>Native shape: {detail.source.shape.join(' × ')} · units: {detail.source.units}</p>
        {!detail.source_current&&<p className="notice error" role="alert">{detail.source_unavailable_reason} Saving and download are blocked.</p>}
        <button ref={viewerButton} className="btn btn-primary" disabled={busy||!detail.source_current||viewerOpen} onClick={()=>setViewerOpen(true)}>Open blinded original CT viewer</button>
        <button className="btn btn-ghost" disabled={busy||!detail.source_current} onClick={download}><Download size={16}/>Download verified original CT</button>
        <p>The embedded viewer and download use only the original CT. No prediction-overlay viewer is used; anatomical interpretation is not certified.</p>
        {viewerOpen&&<Suspense fallback={<p role="status">Opening original CT viewer…</p>}><BlindedCtViewer assignment={detail} ownerId={user.id}
          onClose={()=>{restoreViewerFocus.current=true;setViewerOpen(false);}}/></Suspense>}
        <label>Private unverified preparation notes<textarea className="form-input" aria-label="Private unverified preparation notes" rows={5}
          value={notes} onChange={e=>setNotes(e.target.value)} disabled={busy||!detail.source_current}/></label>
        <p>Server revision: {saved.revision}. Notes are mutable preparation, not a clinical annotation, report or training label.</p>
        <button className="btn btn-primary" disabled={busy||conflict||!detail.source_current||Array.from(notes).length>4000}
          onClick={save}><Save size={16}/>Save private review draft</button>
        {conflict&&<div className="notice error" role="alert"><p>A conflict or uncertain save outcome occurred. Your text is retained. Copy any unsaved text privately before explicitly replacing it.</p>
          <button className="btn btn-ghost" disabled={busy} onClick={()=>load(currentItem)}>Reload latest and replace my notes</button></div>}
      </>}
    </Panel>
    {user.role==='Admin'&&<Panel title="Coordinator: assign independent accounts" description="Bindings are frozen. No withdrawal, reassignment or review findings endpoint is implemented.">
      <form onSubmit={assign}>
        <label>Case<select className="form-select" aria-label="Review case" value={caseId} disabled={busy} onChange={e=>{setCaseId(e.target.value);setPreview(null);setCreated(null);}}>
          <option value="">Select an existing CT case</option>{cases.map(c=><option key={c.id} value={c.id}>{c.case_code} · {c.id}</option>)}
        </select></label>
        <button type="button" className="btn btn-ghost" disabled={busy||!caseId} onClick={inspect}>Inspect original CT identity</button>
        {preview&&<p style={{overflowWrap:'anywhere'}}>Verified original CT SHA-256: {preview.source.source_sha256}</p>}
        {['R1','R2'].map((slot,i)=><label key={slot}>{slot} reviewer<select className="form-select" aria-label={`${slot} reviewer`} value={i===0?r1:r2} disabled={busy} onChange={e=>(i===0?setR1:setR2)(e.target.value)} required>
          <option value="">Select an active Clinician account</option>{readers.map(r=><option key={r.id} value={r.id}>{r.full_name} · account {r.id}</option>)}
        </select></label>)}
        <label>Protocol version<input className="form-input" value={protocol} aria-label="Protocol version" onChange={e=>setProtocol(e.target.value)} maxLength={128} required disabled={busy}/></label>
        <label><input type="checkbox" checked={ack} onChange={e=>setAck(e.target.checked)} disabled={busy}/>I understand that accounts become CT-only, known prior workspace access is disqualifying, and qualification and human independence remain unverified.</label>
        <p>Use separately identified reviewers without prior case/AI exposure. Do not create another account to disguise the same person’s prior knowledge. First 500 users are listed.</p>
        <button className="btn btn-primary" disabled={busy||!preview||!ack||!r1||!r2||r1===r2||!protocol.trim()}>Create R1/R2 assignments</button>
      </form>
      {created&&<div role="status"><p>Case {created.case_id} assigned. Only assignment metadata is shown.</p>{created.assignments.map(row=><p key={row.id}>{row.slot}: {row.id}</p>)}</div>}
    </Panel>}
  </>;
}
