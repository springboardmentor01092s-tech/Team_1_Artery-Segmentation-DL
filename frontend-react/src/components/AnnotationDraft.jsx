import { useLayoutEffect, useMemo, useRef, useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { CLINICAL_WRITERS } from '../constants/permissions';
import { segmentationApi } from '../api/segmentation';
import { authApi } from '../api/auth';
import { annotationDraftsApi } from '../api/annotation-drafts';
import { annotationBinding, annotationDocumentSnapshot } from '../api/annotation-drafts-contract';
import { saveArtifact } from '../lib/segmentation';
import { annotationSource, annotationDraftBlob, newAnnotationDraft, newDraftLesion,
  validateAnnotationDraft, worldToNativeIjk, POINT_FIELDS, SEVERITY_CHOICES, MAX_ANNOTATION_DRAFT_BYTES } from '../lib/annotation-draft';

const pointNames = ['Lesion center','Proximal boundary','Distal boundary','Minimum caliper start',
  'Minimum caliper end','Reference caliper start','Reference caliper end'];

export default function AnnotationDraft({ caseId, result, geometry, location }) {
  const { user } = useAuth();
  const source = useMemo(() => annotationSource(caseId,result,geometry),[caseId,result,geometry]);
  const sourceKey = JSON.stringify(source);
  // Private server state and unsaved local content never survive an account,
  // role or source transition, even if the surrounding viewer stays mounted.
  return <AnnotationDraftWorkspace key={`${user?.id}:${user?.role}:${sourceKey}`}
    caseId={caseId} result={result} location={location} source={source} sourceKey={sourceKey}/>;
}

function AnnotationDraftWorkspace({caseId,result,location,source,sourceKey}) {
  const { user, isRole } = useAuth();
  const [draft,setDraft] = useState(() => newAnnotationDraft(source));
  const [selected,setSelected] = useState(0), [error,setError] = useState(''), [notice,setNotice] = useState('');
  const [pending,setPending] = useState(null);
  const [server,setServer] = useState(null), [serverChoices,setServerChoices] = useState([]);
  const [serverId,setServerId] = useState(''), [nextOffset,setNextOffset] = useState(null);
  const [conflict,setConflict] = useState(null), [uncertainCreate,setUncertainCreate] = useState(false);
  const busy = pending !== null && pending.owner===user && pending.sourceKey===sourceKey;
  const session=useRef({alive:false,generation:0,operation:null,user:null,sourceKey:null});
  useLayoutEffect(()=>{
    const state=session.current;
    state.alive=true;state.generation++;state.user=user;state.sourceKey=sourceKey;
    const invalidate=event=>{
      if (event.type==='storage' && (event.storageArea && event.storageArea!==localStorage
          || event.key!==null && event.key!=='vascuai_token')) return;
      state.generation++;state.operation?.controller.abort();state.operation=null;
      setPending(null);setError('Viewer or session changed. Reopen the current study before continuing.');
    };
    window.addEventListener('storage',invalidate);
    window.addEventListener('vascuai:unauthorized',invalidate);
    return()=>{
      state.alive=false;state.generation++;state.operation?.controller.abort();state.operation=null;
      window.removeEventListener('storage',invalidate);
      window.removeEventListener('vascuai:unauthorized',invalidate);
    };
  },[user,sourceKey]);
  const lesion = draft.proposed_lesions[selected];
  if (!isRole(...CLINICAL_WRITERS)) return <p className="text-sm">Local lesion worksheet entry is available to Clinician and Admin roles. No expert labels are assumed.</p>;
  function update(field,value) {
    setNotice('');
    setDraft(current => ({...current,proposed_lesions:current.proposed_lesions.map((row,i) => i===selected?{...row,[field]:value}:row)}));
  }
  function capture(field) {
    try { update(field,worldToNativeIjk(location?.world,draft.source,source));setError(''); }
    catch(e) { setError(e.message); }
  }
  function checkOperation(op) {
    const state=session.current;
    if (!state.alive || state.operation!==op || state.generation!==op.generation || op.controller.signal.aborted
        || op.token!==localStorage.getItem('vascuai_token') || state.sourceKey!==op.sourceKey
        || state.user?.id!==op.userId || state.user?.role!==op.role || !CLINICAL_WRITERS.includes(state.user?.role)) {
      op.controller.abort();
      throw new Error('Viewer or session changed. Reopen the current study before continuing.');
    }
  }
  function beginOperation() {
    const state=session.current;
    // A ref prevents duplicate operations even before React commits disabled controls.
    if (state.operation) return null;
    const op={owner:user,generation:state.generation,token:localStorage.getItem('vascuai_token'),userId:user?.id,
      role:user?.role,sourceKey,controller:new AbortController()};
    state.operation=op;
    try { checkOperation(op);if (!op.token) throw new Error('Your session changed. Sign in before continuing.'); }
    catch(e) { state.operation=null;setError(e.message);return null; }
    setPending(op);setError('');setNotice('');
    return op;
  }
  function operationError(op,error) {
    if (session.current.alive && session.current.operation===op) setError(error.message);
  }
  function finishOperation(op) {
    if (session.current.alive && session.current.operation===op) {
      session.current.operation=null;setPending(null);
    }
  }
  async function fresh(op) {
    checkOperation(op);
    const identity=await authApi.me({signal:op.controller.signal,timeout:15000});
    checkOperation(op);
    if (identity?.id!==op.userId || identity.role!==op.role || !CLINICAL_WRITERS.includes(identity.role)) {
      throw new Error('Writer authorization changed. Sign in again before continuing.');
    }
    const rows = await segmentationApi.list(caseId,{signal:op.controller.signal});
    checkOperation(op);
    if (!rows.some(row => row.id===result.id && row.case_id===source.case_id && row.stale===false
        && row.metadata?.source_sha256===source.source_sha256)) {
      throw new Error('Source freshness could not be verified. Refresh the case and use a current saved run.');
    }
  }
  async function download() {
    const op=beginOperation();if (!op) return;
    try {
      await fresh(op);checkOperation(op);
      const blob=annotationDraftBlob(draft,source);
      checkOperation(op);
      saveArtifact({blob,filename:`case-${source.case_id}-unverified-lesion-draft.json`});
      setNotice('Draft download handed to your browser. This is not a server-saved review or expert ground truth.');
    } catch(e) { operationError(op,e); }
    finally { finishOperation(op); }
  }
  async function restore(event) {
    const file=event.target.files[0];event.target.value='';
    if (!file) return;
    const op=beginOperation();if (!op) return;
    try {
      if (file.size>MAX_ANNOTATION_DRAFT_BYTES || file.size===0) throw new Error('Choose a nonempty annotation draft JSON no larger than 2 MiB.');
      const value=JSON.parse(await file.text());
      checkOperation(op);
      validateAnnotationDraft(value,source);await fresh(op);checkOperation(op);setDraft(value);setSelected(0);
      setNotice('Source-matched local draft restored. The server is unchanged until you explicitly save. Reviewer qualification and clinical correctness remain unverified.');
    } catch(e) { operationError(op,e); }
    finally { finishOperation(op); }
  }
  function serverContext(op) {
    return {source,ownerId:op.userId,checkpointSha256:result.metadata?.checkpoint_sha256};
  }
  function adoptServer(value) {
    setServer({id:value.id,revision:value.revision,binding:annotationBinding(value)});
    const item={id:value.id,case_id:value.case_id,owner_id:value.owner_id,revision:value.revision,
      segmentation_result_id:value.document.source.segmentation_result_id,source_sha256:value.document.source.source_sha256,
      status:value.status,updated_at:value.updated_at,clinical_gate_authorized:false,training_release_authorized:false};
    setServerChoices(current=>current.some(row=>row.id===value.id)
      ?current.map(row=>row.id===value.id?item:row):[item,...current]);
    setServerId(value.id);setConflict(null);setUncertainCreate(false);
  }
  async function discoverServerDrafts(offset=0) {
    const op=beginOperation();if(!op)return;
    try {
      await fresh(op);checkOperation(op);
      const value=await annotationDraftsApi.list(serverContext(op),offset,{signal:op.controller.signal});
      checkOperation(op);
      setServerChoices(current=>offset===0?value.items:[...current.filter(row=>!value.items.some(item=>item.id===row.id)),...value.items]);
      setNextOffset(value.next_offset);
      setNotice(value.items.length?'Your private drafts for this saved run are listed. Load one explicitly; local edits have not changed.'
        :'No private drafts on this page for the current saved run. Local edits have not changed.');
      if(value.offset_limit_reached)setError('The draft-list pagination bound was reached. No further page is available.');
    } catch(e) {operationError(op,e);}
    finally {finishOperation(op);}
  }
  async function loadServerDraft(id=serverId) {
    if(!id){setError('Select or enter your saved server draft ID first.');return;}
    const op=beginOperation();if(!op)return;
    try {
      await fresh(op);checkOperation(op);
      const value=await annotationDraftsApi.read(serverContext(op),id,{signal:op.controller.signal,
        binding:server?.id===id?server.binding:undefined});
      checkOperation(op);
      if(!value.source_current)throw new Error('Saved source is stale or unverifiable. Local edits were kept; refresh the case and viewer.');
      setDraft(value.document);setSelected(0);adoptServer(value);
      setNotice(`Loaded your private server draft at revision ${value.revision}. Local edits were replaced by your explicit load; clinical and training release remain unauthorized.`);
    } catch(e) {operationError(op,e);}
    finally {finishOperation(op);}
  }
  async function saveServerDraft() {
    if(conflict || uncertainCreate || serverId && server?.id!==serverId)return;
    const op=beginOperation();if(!op)return;
    let writeStarted=false;
    try {
      const snapshot=annotationDocumentSnapshot(draft,source);
      await fresh(op);checkOperation(op);writeStarted=true;
      const value=await annotationDraftsApi.save(serverContext(op),snapshot,server,{signal:op.controller.signal});
      checkOperation(op);setDraft(value.document);adoptServer(value);
      setNotice(`Saved your private server draft at revision ${value.revision}. This is unverified preparation, not a submitted review.`);
    } catch(e) {
      if(session.current.alive && session.current.operation===op && writeStarted) {
        const status=e.response?.status;
        if(status===409 || status===404 || !status || status>=500) {
          if(server || status===409)setConflict({id:server?.id||null});
          else setUncertainCreate(true);
        }
      }
      operationError(op,e);
    } finally {finishOperation(op);}
  }
  function separateServerDraft() {
    setServer(null);setServerId('');setConflict(null);setUncertainCreate(false);setError('');
    setNotice('Local edits retained. The next Save creates a separate private draft; it does not modify the previous record and may duplicate an unconfirmed creation.');
  }
  return <details className="no-print" aria-label="Local lesion annotation draft">
    <summary>Prepare a local lesion review draft</summary>
    <p className="notice">Unverified reader preparation only. No diagnosis, expert ground truth, clinical validation or quantitative gate approval. The predicted segmentation is available in this workspace; this is not a blinded independent reading.</p>
    <p>Edits stay in memory until you save a private server draft or download local JSON. Server drafts are private to your account and survive logout. Neither form is included in normal reports.</p>
    <p>Coordinates below use the original CT native IJK grid (zero based), not displayed RAS axis indices. Caliper endpoints are bookmarks; no diameter, percentage or severity is calculated.</p>
    <p className="text-xs" style={{overflowWrap:'anywhere'}}>Original CT SHA-256: {source.source_sha256}</p>
    {error && <p role="alert" className="notice error">{error}</p>}
    {notice && <p role="status" className="notice">{notice}</p>}
    <fieldset disabled={busy} style={{minWidth:0}} aria-label="Private server drafts">
      <legend>Private server drafts — unverified preparation</legend>
      <p>Loading replaces unsaved local edits. Download local JSON first if you need to keep them. Saving uses the loaded revision; conflicts never trigger an automatic retry.</p>
      <button type="button" className="btn btn-ghost" onClick={()=>discoverServerDrafts()}>Refresh my saved drafts</button>
      {nextOffset!==null && <button type="button" className="btn btn-ghost" onClick={()=>discoverServerDrafts(nextOffset)}>Load more of my drafts</button>}
      <label>Saved private draft<select className="form-select" value={serverId} onChange={e=>setServerId(e.target.value)}>
        <option value="">Select a saved draft</option>
        {serverId && !serverChoices.some(row=>row.id===serverId) && <option value={serverId}>{serverId}</option>}
        {serverChoices.map(row=><option key={row.id} value={row.id}>{row.id} · revision {row.revision}</option>)}
      </select></label>
      <label>Server draft ID<input className="form-input" maxLength={36} value={serverId} onChange={e=>setServerId(e.target.value.trim())}/></label>
      <div className="page-actions">
        <button type="button" className="btn btn-primary" onClick={saveServerDraft}
          disabled={Boolean(busy||conflict||uncertainCreate||serverId && server?.id!==serverId)}>Save private server draft</button>
        <button type="button" className="btn btn-ghost" disabled={!serverId} onClick={()=>loadServerDraft()}>Load selected server draft and replace local edits</button>
        <button type="button" className="btn btn-ghost" onClick={separateServerDraft}>Start a separate server draft from local edits</button>
      </div>
      {server && <p className="text-xs" style={{overflowWrap:'anywhere'}}>Editing private draft {server.id}, based on revision {server.revision}.</p>}
      {conflict && <div className="notice error" aria-label="Server draft conflict">
        <p>Save conflict or unconfirmed update. Your local edits were kept. Download local JSON, then explicitly reload the latest server draft and resolve your changes. Nothing is automatically merged or overwritten.</p>
        {conflict.id?<button type="button" className="btn btn-ghost" onClick={()=>loadServerDraft(conflict.id)}>Reload latest and replace local edits</button>
          :<p>Refresh case inputs and reopen a current viewer before saving this source.</p>}
      </div>}
      {uncertainCreate && <p className="notice error">Creation could not be confirmed. Refresh your saved drafts and load the matching record before retrying. Starting a separate draft is an explicit choice that may create a duplicate.</p>}
      {serverId && server?.id!==serverId && <p>Load the selected draft before saving changes to it.</p>}
    </fieldset>
    <div className="form-grid">
      <label>Reviewer reference (unverified)<input className="form-input" maxLength={200} disabled={busy} value={draft.reviewer_reference}
        onChange={e=>setDraft({...draft,reviewer_reference:e.target.value})}/></label>
      <label>Clinical protocol reference (not approved here)<input className="form-input" maxLength={500} disabled={busy} value={draft.protocol_reference}
        onChange={e=>setDraft({...draft,protocol_reference:e.target.value})}/></label>
    </div>
    <div className="page-actions">
      <button type="button" className="btn btn-ghost" disabled={busy || draft.proposed_lesions.length>=100} onClick={()=>{
        setDraft({...draft,proposed_lesions:[...draft.proposed_lesions,newDraftLesion()]});setSelected(draft.proposed_lesions.length);setNotice('');
      }}>Add proposed lesion worksheet</button>
      <button type="button" className="btn btn-primary" disabled={busy} onClick={download}>Download unverified draft JSON</button>
      <label style={{display:'block',maxWidth:'100%',minWidth:0}}>Restore draft JSON<input style={{display:'block',maxWidth:'100%'}} type="file" accept=".json,application/json" aria-label="Restore annotation draft JSON" disabled={busy} onChange={restore}/></label>
    </div>
    {!lesion ? <p>No lesion worksheet added. This does not mean that stenosis is absent.</p> : <fieldset disabled={busy} style={{minWidth:0}}>
      <legend>Proposed lesion worksheet — not a confirmed finding</legend>
      <button type="button" className="btn btn-ghost btn-sm" onClick={()=>{
        setDraft({...draft,proposed_lesions:draft.proposed_lesions.filter((_,i)=>i!==selected)});
        setSelected(Math.max(0,selected-1));setNotice('');
      }}>Remove selected worksheet</button>
      <label>Worksheet<select className="form-select" value={selected} onChange={e=>setSelected(Number(e.target.value))}>
        {draft.proposed_lesions.map((row,i)=><option key={row.draft_id} value={i}>Worksheet {i+1}</option>)}
      </select></label>
      <div className="form-grid">
        <label>Coronary artery<select className="form-select" value={lesion.artery} onChange={e=>update('artery',e.target.value)}>
          <option value="">Not recorded</option>{['LM','LAD','LCx','RCA','graft','other'].map(x=><option key={x}>{x}</option>)}
        </select></label>
        <label>Coronary segment<input className="form-input" maxLength={200} value={lesion.segment} onChange={e=>update('segment',e.target.value)}/></label>
        <label>Segment naming convention<input className="form-input" maxLength={200} value={lesion.segment_convention} onChange={e=>update('segment_convention',e.target.value)}/></label>
      </div>
      <ul>{POINT_FIELDS.map((field,i)=><li key={field} style={{marginBlock:8}}>
        <button type="button" className="btn btn-ghost btn-sm" disabled={!location} onClick={()=>capture(field)}>Capture {pointNames[i]}</button>{' '}
        <span>{lesion[field] ? `Native IJK: ${lesion[field].join(', ')}` : 'Not recorded'}</span>
        {lesion[field] && <button type="button" className="btn btn-ghost btn-sm" onClick={()=>update(field,null)} aria-label={`Clear ${pointNames[i]}`}>Clear</button>}
      </li>)}</ul>
      <div className="form-grid">{[['minimum_lumen_diameter_mm','Minimum lumen diameter (mm)'],['adjacent_reference_diameter_mm','Adjacent reference diameter (mm)'],['percentage_narrowing','Reader-entered percentage narrowing']].map(([key,label])=><label key={key}>{label}
        <input className="form-input" type="number" min="0" max={key==='percentage_narrowing'?'100':undefined} step="any" value={lesion[key]??''}
          onChange={e=>update(key,e.target.value===''?null:Number(e.target.value))}/></label>)}
        <label>Reference selection and rationale<input className="form-input" maxLength={500} value={lesion.reference_selection} onChange={e=>update('reference_selection',e.target.value)}/></label>
        <label>Percentage measurement basis<input className="form-input" maxLength={500} value={lesion.percentage_basis} onChange={e=>update('percentage_basis',e.target.value)}/></label>
        <label>Reader-entered severity (unverified)<select className="form-select" value={lesion.severity_category??''} onChange={e=>update('severity_category',e.target.value||null)}>
          <option value="">Not recorded</option>{SEVERITY_CHOICES.map(x=><option key={x}>{x}</option>)}
        </select></label>
      </div>
      <label>Unavailable values and limitations<textarea className="form-textarea" maxLength={1000} required value={lesion.unavailable_reason} onChange={e=>update('unavailable_reason',e.target.value)}/></label>
      <label>Draft notes (no identifying information)<textarea className="form-textarea" maxLength={1000} value={lesion.notes} onChange={e=>update('notes',e.target.value)}/></label>
    </fieldset>}
  </details>;
}
