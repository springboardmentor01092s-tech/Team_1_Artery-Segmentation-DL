import {useEffect,useRef,useState} from 'react';
import {reviewAssignmentsApi} from '../api/review-assignments';
import {loadAssignedCt} from '../lib/ct-review-loader';
import {createCtReviewViewer} from '../lib/ct-review-adapter';
import {graphicsCapabilities,releaseViewer} from '../lib/niivue-adapter';
import ReviewAnnotationForm from './ReviewAnnotationForm';
import {volumeBudget} from '../lib/volume-geometry';

const independentAccess={
  detail:(item,owner,options)=>reviewAssignmentsApi.detail(item,owner,options),
  load:(item,owner,options)=>loadAssignedCt(reviewAssignmentsApi,item,owner,options),
};
export default function BlindedCtViewer(props){
  return <VerifiedOriginalCtViewer {...props}/>;
}
// Shared display only. Each workflow retains its own authenticated source loader.
export function VerifiedOriginalCtViewer(props){
  const [attempt,setAttempt]=useState(0);
  return <Session key={attempt} {...props} onRetry={()=>setAttempt(n=>n+1)}/>;
}
function Session({assignment,ownerId,onClose,onRetry,access=independentAccess,adjudication=false}){
  const canvas=useRef(null),heading=useRef(null),instance=useRef(null);
  const [ready,setReady]=useState(false),[error,setError]=useState(''),[phase,setPhase]=useState('Checking original CT identity…');
  const [location,setLocation]=useState(null),[progress,setProgress]=useState(null),[view,setView]=useState('slices');
  const [volumeCount,setVolumeCount]=useState(0);
  const [externalOnly,setExternalOnly]=useState(false);
  const [width,setWidth]=useState(1000),[level,setLevel]=useState(300),[pan,setPan]=useState([0,0,0,1]);
  const failure=useRef(null);
  useEffect(()=>{heading.current?.focus({preventScroll:true});},[]);
  useEffect(()=>{
    const controller=new AbortController(),token=localStorage.getItem('vascuai_token'),element=canvas.current;
    let alive=true,viewer,failed=false;
    const current=()=>alive&&!controller.signal.aborted&&token===localStorage.getItem('vascuai_token');
    const fail=(message,allowExternal=false)=>{
      if(!alive||failed)return;failed=true;controller.abort();releaseViewer(viewer);instance.current=null;
      setReady(false);setLocation(null);setError(message);setExternalOnly(allowExternal);
    };
    failure.current=fail;
    const session=()=>{if(alive&&token!==localStorage.getItem('vascuai_token'))fail('Your session changed. Close the CT viewer and sign in again.');};
    const fresh=async()=>{
      if(!current()){session();return;}
      try{const next=await access.detail(assignment,ownerId,{signal:controller.signal});
        if(current()&&!next.source_current)fail('The bound original CT is unavailable or changed. Close and reload the assignment.');
      }catch{if(current())fail('CT access or source freshness could not be verified. Close and reload the assignment.');}
    };
    const lost=event=>{event.preventDefault();if(!controller.signal.aborted)fail('The GPU context was lost. Reopen the CT viewer or use the verified download.');};
    element.addEventListener('webglcontextlost',lost);
    (async()=>{
      try{
        try{
          graphicsCapabilities(assignment.source.shape);
          volumeBudget(assignment.source.shape,globalThis.navigator?.deviceMemory||8);
        }catch(preflight){if(current())fail(preflight.message,true);return;}
        const packet=await access.load(assignment,ownerId,{signal:controller.signal,
          onPhase:value=>{if(current())setPhase(value);},onProgress:value=>{if(current())setProgress(value);}});
        if(!current()){session();return;}
        viewer=await createCtReviewViewer(element,packet,value=>{if(current())setLocation(value);},controller.signal);
        if(!current()){releaseViewer(viewer);session();return;}
        instance.current=viewer;setVolumeCount(viewer.volumes.length);setReady(true);setPhase('');
      }catch(e){if(alive&&!controller.signal.aborted)fail(e.message||'Original CT could not be displayed.');}
    })();
    window.addEventListener('storage',session);window.addEventListener('vascuai:unauthorized',session);window.addEventListener('focus',fresh);
    const timer=setInterval(fresh,60000),sessionTimer=setInterval(session,500);
    return ()=>{
      alive=false;controller.abort();clearInterval(timer);clearInterval(sessionTimer);element.removeEventListener('webglcontextlost',lost);
      window.removeEventListener('storage',session);window.removeEventListener('vascuai:unauthorized',session);window.removeEventListener('focus',fresh);
      releaseViewer(viewer);instance.current=null;failure.current=null;
    };
  },[assignment,ownerId,access]);
  const operate=fn=>{try{if(instance.current)fn(instance.current);}catch{failure.current?.('CT rendering failed. Close the viewer or use the verified download.');}};
  const slice=(axis,value)=>operate(v=>{const next=[...v.scene.crosshairPos];next[axis]=(Number(value)+.5)/location.dimensions[axis];
    v.scene.crosshairPos=next;v.drawScene();v.onLocationChange();});
  const changeView=value=>operate(v=>{v.setSliceType({slices:v.sliceTypeMultiplanar,axial:v.sliceTypeAxial,coronal:v.sliceTypeCoronal,sagittal:v.sliceTypeSagittal}[value]);setView(value);});
  const windowing=(w,l)=>operate(v=>{v.volumes[0].cal_min=l-w/2;v.volumes[0].cal_max=l+w/2;v.updateGLVolume();setWidth(w);setLevel(l);});
  const positioning=value=>operate(v=>{v.setPan2Dxyzmm(value);setPan(value);});
  const reset=()=>{positioning([0,0,0,1]);windowing(1000,300);changeView('slices');operate(v=>{
    v.scene.crosshairPos=location.dimensions.map(n=>(Math.floor(n/2)+.5)/n);v.drawScene();v.onLocationChange();});};
  return <section className="volume-viewer" aria-label={adjudication?'Adjudication original CT viewer':'Blinded original CT viewer'}>
    <div className="volume-viewer-heading"><div><h2 ref={heading} tabIndex={-1}>Original CT only</h2><p>Case {assignment.case_id} · {adjudication?'Third reader':assignment.slot} · unverified reader preparation</p></div>
      <button className="btn btn-ghost" onClick={onClose}>Close original CT viewer</button></div>
    <p className="notice">Original source CT, without predicted masks, AI results or annotation overlays.
      {adjudication?' Frozen R1/R2 records remain separately available in the adjudication workspace.':' No other reviewer’s information is exposed.'}
      Research preparation only; no clinical or training authorization.</p>
    {!error&&phase&&<p role="status">{phase}{progress?` (${(progress.loaded/1024**2).toFixed(1)} MiB received)`:''}</p>}
    {error&&<div className="notice error" role="alert"><p>{error}</p><p>The authenticated original CT download remains a separate option; no prediction viewer is substituted.</p>
      <button className="btn btn-ghost" onClick={onRetry}>Retry original CT viewer</button></div>}
    <div className="volume-canvas-container"><canvas ref={canvas} role="img" aria-label="Original CT slices without overlays" tabIndex={0}
      style={{visibility:ready?'visible':'hidden'}}>Use labelled slice controls. WebGL2 is required.</canvas></div>
    {ready&&<p role="status" data-testid="ct-only-ready">Verified original CT · {volumeCount} volume · no overlays.</p>}
    <fieldset className="volume-controls" disabled={!ready}><legend>Original CT display controls</legend>
      <label>CT view<select aria-label="CT view" value={view} onChange={e=>changeView(e.target.value)}>
        {[['slices','All three planes'],['axial','Axial'],['coronal','Coronal'],['sagittal','Sagittal']].map(([value,label])=><option key={value} value={value}>{label}</option>)}
      </select></label>
      <label>CT window width<input aria-label="CT window width" type="range" min="1" max="3000" value={width} onChange={e=>windowing(Number(e.target.value),level)}/><output>{width}</output></label>
      <label>CT window level<input aria-label="CT window level" type="range" min="-1000" max="1500" value={level} onChange={e=>windowing(width,Number(e.target.value))}/><output>{level}</output></label>
      {[[2,'Axial'],[1,'Coronal'],[0,'Sagittal']].map(([axis,name])=>{const n=location?.dimensions[axis]||1,index=Math.min(n-1,Math.max(0,Math.floor((location?.fraction[axis]||0)*n)));
        return <label key={axis}>{name} CT slice<input aria-label={`${name} CT slice`} type="range" min="0" max={n-1} value={index} step="1" onChange={e=>slice(axis,e.target.value)}/><output>{index+1} / {n}</output></label>;})}
      <button className="btn btn-ghost" disabled={pan[3]>=3} onClick={()=>positioning([...pan.slice(0,3),Math.min(3,pan[3]+.25)])}>Zoom CT in</button>
      <button className="btn btn-ghost" disabled={pan[3]<=.5} onClick={()=>positioning([...pan.slice(0,3),Math.max(.5,pan[3]-.25)])}>Zoom CT out</button>
      <button className="btn btn-ghost" onClick={()=>positioning([pan[0]-10,pan[1],pan[2],pan[3]])}>Pan CT left</button>
      <button className="btn btn-ghost" onClick={()=>positioning([pan[0]+10,pan[1],pan[2],pan[3]])}>Pan CT right</button>
      <button className="btn btn-ghost" onClick={()=>positioning([pan[0],pan[1]+10,pan[2],pan[3]])}>Pan CT up</button>
      <button className="btn btn-ghost" onClick={()=>positioning([pan[0],pan[1]-10,pan[2],pan[3]])}>Pan CT down</button>
      <button className="btn btn-ghost" onClick={reset}>Reset CT display</button>
    </fieldset>
    {ready&&location&&<><p>Crosshair RAS: {location.world.map(n=>n.toFixed(2)).join(', ')} mm.</p>
      <p>Native IJK: {location.native?.join(', ')||'outside original voxel centres'}. Display position only; no lesion recorded.</p>
      <p>Original spacing: {location.spacing.map(n=>n.toFixed(4)).join(' × ')} mm. Intensity window uses original source scaling.</p></>}
    <p>Neurological convention. Slice controls follow anatomical RAS axes, not necessarily original array order.
      The thin red crosshair marks navigation only. Browser memory and orthogonal-geometry limits remain enforced.</p>
    {externalOnly&&<p className="notice">The display resource check stopped before CT download. Use the verified original CT download in an approved desktop viewer.
      {adjudication?' Record manual decisions in the separate adjudication worksheet; this pane does not create new independent-reader annotations.':' Then manually enter its original zero-based native IJK coordinates below.'}
      No image, landmark or measurement is inferred here.</p>}
    {!adjudication&&(ready&&location||externalOnly)&&<ReviewAnnotationForm key={`${assignment.id}:${assignment.source.source_sha256}`} assignment={assignment} location={ready?location:null}/>}
  </section>;
}
