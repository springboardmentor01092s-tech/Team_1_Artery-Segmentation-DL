import {useEffect,useLayoutEffect,useRef,useState} from 'react';
import {useAuth} from '../context/AuthContext';
import {reviewAssignmentsApi} from '../api/review-assignments';
import {reviewAnnotationsApi} from '../api/review-annotations';
import {newReviewAnnotation,newReaderLesion,reviewAnnotationBlob,validateReviewAnnotation,manualNativeLandmark} from '../lib/review-annotation';
import {POINT_FIELDS,worldToNativeGeometry} from '../lib/annotation-draft';
import {saveArtifact} from '../lib/segmentation';
const pointNames=['Lesion center','Proximal boundary','Distal boundary','Minimum caliper start','Minimum caliper end','Reference caliper start','Reference caliper end'];

function ManualLandmark({name,value,onApply}){
  const [text,setText]=useState(value===null?'':value.join(', '));
  return <><label>Manual {name} native IJK<input className="form-input" aria-label={`Manual ${name} native IJK`}
    value={text} maxLength={200} placeholder="i, j, k (zero-based)" onChange={e=>setText(e.target.value)}/></label>
    <button className="btn btn-ghost" onClick={()=>onApply(text)}>Apply manual {name}</button></>;
}

export default function ReviewAnnotationForm({assignment,location}){
  const {user}=useAuth(),sourceKey=JSON.stringify(assignment.source);
  const [document,setDocument]=useState(()=>newReviewAnnotation(assignment)),[selected,setSelected]=useState(0),[revision,setRevision]=useState(0);
  const [busy,setBusy]=useState(true),[error,setError]=useState(''),[notice,setNotice]=useState(''),[conflict,setConflict]=useState(false);
  const [submitted,setSubmitted]=useState(false),[savedDocument,setSavedDocument]=useState(''),[documentHash,setDocumentHash]=useState(null),[acknowledge,setAcknowledge]=useState(false),[recordHash,setRecordHash]=useState(null);
  const [amendmentHistory,setAmendmentHistory]=useState(null),[amendmentMode,setAmendmentMode]=useState(false),[amendmentDocument,setAmendmentDocument]=useState(null),[amendmentReason,setAmendmentReason]=useState('');
  const session=useRef({alive:false,generation:0,operation:null});
  useLayoutEffect(()=>{
    const state=session.current;state.alive=true;state.generation++;
    const invalidate=event=>{
      if(event?.type==='storage'&&event.key!==null&&event.key!=='vascuai_token')return;
      state.generation++;state.operation?.controller.abort();
    };
    window.addEventListener('storage',invalidate);window.addEventListener('vascuai:unauthorized',invalidate);
    return()=>{state.alive=false;invalidate();state.operation=null;window.removeEventListener('storage',invalidate);window.removeEventListener('vascuai:unauthorized',invalidate);};
  },[user,sourceKey]);
  const workingDocument=amendmentMode?amendmentDocument:document;
  const row=workingDocument?.lesions?.[selected];
  const update=(key,value)=>{
    const setter=amendmentMode?setAmendmentDocument:setDocument;
    setter(d=>({...d,lesions:d.lesions.map((v,i)=>i===selected?{...v,[key]:value}:v)}));
  };
  const check=op=>{
    if(!session.current.alive||session.current.operation!==op||session.current.generation!==op.generation||op.controller.signal.aborted
      ||op.token!==localStorage.getItem('vascuai_token'))throw new Error('Session or source changed. Reopen the current CT before continuing.');
  };
  const operate=async fn=>{
    if(session.current.operation)return;
    const op={controller:new AbortController(),generation:session.current.generation,token:localStorage.getItem('vascuai_token')};
    session.current.operation=op;setBusy(true);setError('');setNotice('');
    try{
      check(op);const current=await reviewAssignmentsApi.detail(assignment,user.id,{signal:op.controller.signal});check(op);
      if(!current.source_current)throw new Error('Assigned original CT is unavailable or changed.');
      await fn(op);check(op);
    }catch(e){if(session.current.alive&&session.current.operation===op)setError(e.message);}
    finally{if(session.current.alive&&session.current.operation===op){session.current.operation=null;setBusy(false);}}
  };
  const load=()=>operate(async op=>{
    const result=await reviewAnnotationsApi.read(assignment,user.id,{signal:op.controller.signal});check(op);
    if(!result.source_current)throw new Error('Bound CT changed. Draft is retained on the server.');
    let frozen=null;
    let amendmentRows=null;
    if(result.submitted){
      [frozen,amendmentRows]=await Promise.all([
        reviewAnnotationsApi.submission(assignment,user.id,{signal:op.controller.signal}),
        reviewAnnotationsApi.amendments(assignment,user.id,{signal:op.controller.signal})]);check(op);
      if(frozen.submission.annotation_revision!==result.revision||frozen.submission.document_sha256!==result.content_sha256
        ||amendmentRows.submission_sha256!==frozen.record_sha256)throw new Error('Frozen review or amendment history does not match its retained parent');
    }
    setDocument(result.document||newReviewAnnotation(assignment));setRevision(result.revision);setSelected(0);setConflict(false);
    setSubmitted(result.submitted);setDocumentHash(result.content_sha256);setSavedDocument(JSON.stringify(result.document));setAcknowledge(false);
    setRecordHash(frozen?.record_sha256||null);setAmendmentHistory(amendmentRows);setAmendmentMode(false);setAmendmentDocument(null);setAmendmentReason('');
    setNotice(`Loaded your formal draft at revision ${result.revision}. Clinical correctness remains unverified.`);
  });
  const save=()=>operate(async op=>{
    validateReviewAnnotation(document,assignment);
    try{
      const result=await reviewAnnotationsApi.save(assignment,user.id,document,revision,{signal:op.controller.signal});check(op);
      setDocument(result.document);setRevision(result.revision);setNotice(`Formal unverified draft saved at revision ${result.revision}.`);
      setDocumentHash(result.content_sha256);setSavedDocument(JSON.stringify(result.document));setAcknowledge(false);
    }catch(e){check(op);if(![400,401,403,404,413,422].includes(e.response?.status))setConflict(true);throw e;}
  });
  const capture=key=>operate(async op=>{const point=worldToNativeGeometry(location?.world,assignment.source);check(op);update(key,point);});
  const manual=(key,text)=>operate(async op=>{const point=manualNativeLandmark(text,assignment.source);check(op);update(key,point);
    setNotice('Manual native-IJK point recorded against the assigned CT geometry. Clinical correctness remains unverified.');});
  const download=()=>operate(async op=>{
    const blob=reviewAnnotationBlob(workingDocument,assignment);check(op);
    saveArtifact({blob,filename:`case-${assignment.case_id}-${assignment.slot}-${amendmentMode?'amendment':'unverified-review'}.json`});setNotice('Source-bound unverified worksheet handed to the browser. Server unchanged.');
  });
  const restore=event=>{
    const file=event.target.files[0];event.target.value='';if(!file)return;
    operate(async op=>{
      if(!file.size||file.size>2*1024*1024)throw new Error('Choose a nonempty source-bound JSON no larger than 2 MiB.');
      const value=JSON.parse(await file.text());check(op);validateReviewAnnotation(value,assignment);
      const current=await reviewAssignmentsApi.detail(assignment,user.id,{signal:op.controller.signal});check(op);
      if(!current.source_current)throw new Error('Bound CT changed.');
      if(amendmentMode)setAmendmentDocument(value);else setDocument(value);setSelected(0);setNotice('Local worksheet restored. No automatic server save was performed.');
    });
  };
  useEffect(()=>{
    let active=true;Promise.resolve().then(()=>{if(active)load();});return()=>{active=false;};
    // The parent keys this workspace to assignment/source and account identity.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  },[]);
  const submit=()=>operate(async op=>{
    validateReviewAnnotation(document,assignment);
    if(!acknowledge||JSON.stringify(document)!==savedDocument)throw new Error('Save local changes and acknowledge immutable submission first.');
    try{
      const result=await reviewAnnotationsApi.submit(assignment,user.id,revision,documentHash,{signal:op.controller.signal});check(op);
      const history=await reviewAnnotationsApi.amendments(assignment,user.id,{signal:op.controller.signal});check(op);
      if(history.revision!==0||history.submission_sha256!==result.record_sha256)throw new Error('New immutable submission did not produce the expected amendment parent history.');
      setSubmitted(true);setRecordHash(result.record_sha256);setAmendmentHistory(history);setNotice('Immutable unverified review submitted. Clinical and training release remain disabled.');
    }catch(e){check(op);setConflict(true);throw e;}
  });
  const startAmendment=()=>{
    const latest=amendmentHistory?.items?.at(-1)?.amendment?.document||document;
    if(!latest||!recordHash)return;
    setAmendmentDocument(structuredClone(latest));setAmendmentReason('');setSelected(0);setConflict(false);setAmendmentMode(true);
    setNotice('Editing a separate unverified addendum. The original submission remains immutable.');
  };
  const cancelAmendment=()=>{setAmendmentMode(false);setAmendmentDocument(null);setAmendmentReason('');setConflict(false);};
  const saveAmendment=()=>operate(async op=>{
    if(!submitted||!amendmentHistory||!recordHash)throw new Error('Reload the immutable submission and amendment history first.');
    if(!amendmentReason.trim())throw new Error('Record why this separate addendum is being made.');
    validateReviewAnnotation(amendmentDocument,assignment);
    try{
      const saved=await reviewAnnotationsApi.appendAmendment(assignment,user.id,recordHash,amendmentDocument,amendmentReason,amendmentHistory,{signal:op.controller.signal});check(op);
      const history=await reviewAnnotationsApi.amendments(assignment,user.id,{signal:op.controller.signal});check(op);
      if(history.revision!==saved.amendment.revision||history.latest_sha256!==saved.record_sha256)throw new Error('Saved amendment is not the verified latest chain head.');
      setAmendmentHistory(history);setAmendmentMode(false);setAmendmentDocument(null);setAmendmentReason('');
      setNotice(`Separate amendment ${saved.amendment.revision} was hash-linked. The immutable submission and any adjudication parents are unchanged.`);
    }catch(e){check(op);if(e.response?.status===409)setConflict(true);throw e;}
  });
  return <section className="card" aria-label="Formal unverified lesion annotation">
    <div className="card-body"><h3>Formal lesion worksheet — manual, unverified</h3>
      <p>No expert qualification or clinical ground truth is implied. Missing values remain null. No diameter, percentage or severity is calculated automatically.</p>
      <p>Clinical gate authorized: false · Training release authorized: false · Server revision: {revision}</p>
      {error&&<p className="notice error" role="alert">{error}</p>}{notice&&<p role="status" aria-label="Formal worksheet status">{notice}</p>}
      <div className="segmentation-downloads">
        <button className="btn btn-ghost" disabled={busy} onClick={load}>{conflict?'Reload latest and replace worksheet':submitted?'Reload immutable submission and amendments':'Load my formal server draft'}</button>
        <button className="btn btn-primary" disabled={busy||conflict||submitted} onClick={save}>Save formal unverified draft</button>
        <button className="btn btn-ghost" disabled={busy} onClick={download}>Download unverified worksheet JSON</button>
        <label>Restore source-bound worksheet JSON<input aria-label="Restore source-bound worksheet JSON" type="file" accept="application/json,.json" disabled={busy||submitted&&!amendmentMode} onChange={restore}/></label>
      </div>
      {conflict&&<p className="notice error" role="alert">Save conflict or uncertain outcome. Local edits are retained. Preserve them privately, then explicitly reload; no automatic overwrite is permitted.</p>}
      {submitted&&<section className="notice" aria-label="Immutable submission amendments"><p>This submitted review is immutable. A later addendum is a separate record and never replaces the submission. {recordHash?`Submission SHA-256: ${recordHash}`:''}</p>
        {amendmentHistory&&<><p>Separate amendments: {amendmentHistory.revision}. Clinical gate authorized: false. Training release authorized: false.</p>
          <ol aria-label="My amendment history">{amendmentHistory.items.map(v=><li key={v.id}>Amendment {v.revision} · {v.record_sha256} · {v.amendment.reason}</li>)}</ol></>}
        {!amendmentMode?<button className="btn btn-ghost" disabled={busy||conflict||!amendmentHistory?.source_current} onClick={startAmendment}>Start a separate unverified amendment</button>:<>
          <p role="note">This addendum will not be shown to an already assigned third reviewer. The API refuses new R3 assignment when an amendment exists.</p>
          <label>Reason for this separate amendment<textarea className="form-input" aria-label="Reason for amendment" maxLength={2000} value={amendmentReason} onChange={e=>setAmendmentReason(e.target.value)} disabled={busy}/></label>
          <button className="btn btn-primary" disabled={busy||conflict||!amendmentReason.trim()||!amendmentHistory?.source_current} onClick={saveAmendment}>Save new immutable amendment</button>
          <button className="btn btn-ghost" disabled={busy} onClick={cancelAmendment}>Cancel amendment editing</button>
        </>}
      </section>}
      <fieldset disabled={busy||submitted&&!amendmentMode}><legend>{amendmentMode?'Separate unverified amendment':'Manual reader entries'}</legend>
        <label>Case assessment<select aria-label="Case assessment" value={workingDocument.case_disposition} onChange={e=>{const setter=amendmentMode?setAmendmentDocument:setDocument;setter(d=>({...d,case_disposition:e.target.value}));}}>
          <option value="not_assessed">Not assessed</option><option value="lesions_proposed">Lesions proposed by reader</option>
          <option value="no_lesion_reported">Reader reports no lesion — unverified</option><option value="ungradable">Ungradable</option>
        </select></label>
        <label>Case unavailable reason<textarea className="form-input" aria-label="Case unavailable reason" value={workingDocument.case_unavailable_reason} maxLength={2000} onChange={e=>{const setter=amendmentMode?setAmendmentDocument:setDocument;setter(d=>({...d,case_unavailable_reason:e.target.value}));}}/></label>
        <button className="btn btn-ghost" disabled={workingDocument.lesions.length>=100} onClick={()=>{setSelected(workingDocument.lesions.length);const setter=amendmentMode?setAmendmentDocument:setDocument;setter(d=>({...d,case_disposition:'lesions_proposed',lesions:[...d.lesions,newReaderLesion()]}));}}>Add manual lesion row</button>
        {workingDocument.lesions.length>0&&<label>Lesion row<select aria-label="Lesion row" value={selected} onChange={e=>setSelected(Number(e.target.value))}>
          {workingDocument.lesions.map((v,i)=><option key={v.draft_id} value={i}>Row {i+1} · {v.draft_id}</option>)}</select></label>}
        {row&&<>
          <div className="form-grid">
            <label>Coronary artery<select aria-label="Coronary artery" value={row.artery} onChange={e=>update('artery',e.target.value)}>
              {['','LM','LAD','LCx','RCA','graft','other'].map(v=><option value={v} key={v}>{v||'Not recorded'}</option>)}</select></label>
            {[['segment','Coronary segment'],['segment_convention','Segment naming convention']].map(([key,name])=><label key={key}>{name}<input className="form-input" aria-label={name} maxLength={200} value={row[key]} onChange={e=>update(key,e.target.value)}/></label>)}
          </div>
          <p>Capture the CT crosshair, or explicitly enter original zero-based native IJK from the verified original CT in an approved external viewer.
            Do not enter RAS/LPS millimetres in these fields. Apply each manual point: unapplied text is not saved or exported.
            These points are manual proposals only; save or download before closing the workspace.</p>
          {POINT_FIELDS.map((key,i)=><div key={key} className="segmentation-downloads">
            <button className="btn btn-ghost" disabled={!location?.world} onClick={()=>capture(key)}>Capture {pointNames[i]}</button>
            <output aria-label={`${pointNames[i]} native IJK`}>{row[key]===null?'Unavailable':row[key].join(', ')}</output>
            <ManualLandmark key={`${row.draft_id}:${key}:${JSON.stringify(row[key])}`} name={pointNames[i]} value={row[key]} onApply={text=>manual(key,text)}/>
            <button className="btn btn-ghost" onClick={()=>update(key,null)}>Clear {pointNames[i]}</button>
          </div>)}
          <div className="form-grid">
            {[['minimum_lumen_diameter_mm','Minimum lumen diameter (mm, manual)'],['adjacent_reference_diameter_mm','Adjacent reference diameter (mm, manual)']].map(([key,name])=><label key={key}>{name}<input className="form-input" aria-label={name} type="number" min="0" step="any" value={row[key]??''} onChange={e=>update(key,e.target.value===''?null:Number(e.target.value))}/></label>)}
            {[['measurement_method','Measurement method',500],['measurement_evidence','Measurement evidence',2000],['reference_selection','Reference selection',500],['percentage_basis','Percentage basis',500],['unavailable_reason','Unavailable measurement reason',1000],['notes','Lesion notes',1000]].map(([key,name,max])=><label key={key}>{name}<textarea className="form-input" aria-label={name} maxLength={max} value={row[key]} onChange={e=>update(key,e.target.value)}/></label>)}
            <p>Percentage narrowing and severity: unavailable. An approved expert-label protocol and qualified review are still required; both fields remain null.</p>
          </div>
          <p>Manual diameter values require both corresponding endpoints, an explicit method and evidence. The software does not infer missing values or validate clinical correctness.</p>
          <button className="btn btn-ghost" onClick={()=>{const setter=amendmentMode?setAmendmentDocument:setDocument;setter(d=>({...d,lesions:d.lesions.filter((_,i)=>i!==selected)}));setSelected(0);}}>Remove unsaved lesion row</button>
        </>}
      </fieldset>
      {!submitted&&<div className="notice"><div>
        <label><input type="checkbox" checked={acknowledge} disabled={busy} onChange={e=>setAcknowledge(e.target.checked)}/>I explicitly freeze this unverified research record. This is not clinical approval or training authorization.</label>
        <p>Submission retains the saved revision, original CT identity, protocol, reviewer and timestamps. It cannot be edited or deleted through this workflow.</p>
        <button className="btn btn-primary" disabled={busy||conflict||revision<1||!documentHash||!acknowledge||JSON.stringify(document)!==savedDocument} onClick={submit}>Submit immutable unverified review</button>
      </div></div>}
    </div>
  </section>;
}
