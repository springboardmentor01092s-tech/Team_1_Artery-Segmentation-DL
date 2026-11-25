// Original-CT preparation only. No prediction, other reader, or clinical release.
const UUID=/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i;
const HASH=/^[a-f0-9]{64}$/;
const positive=n=>Number.isSafeInteger(n)&&n>0&&n<=2147483647;
const fail=()=>{throw new Error('Unverified or mismatched CT review response. Nothing was applied.');};
const detached=value=>JSON.parse(JSON.stringify(value));
const canonical=value=>JSON.stringify(value,(_,v)=>v&&typeof v==='object'&&!Array.isArray(v)
  ?Object.fromEntries(Object.keys(v).sort().map(k=>[k,v[k]])):v);
const exact=(v,keys)=>v&&typeof v==='object'&&!Array.isArray(v)&&Object.keys(v).length===keys.length&&keys.every(k=>Object.hasOwn(v,k));
const flags=['clinical_gate_authorized','training_release_authorized','reader_independence_verified','qualification_verified'];
function unreleased(value){if(flags.some(k=>value[k]!==false))fail();}
function source(value){
  if(!exact(value,['case_id','source_sha256','shape','affine','units'])||!positive(value.case_id)||!HASH.test(value.source_sha256)
    ||value.units!=='mm'||!Array.isArray(value.shape)||value.shape.length!==3||!value.shape.every(positive)
    ||!Number.isSafeInteger(value.shape.reduce((a,b)=>a*b,1))||!Array.isArray(value.affine)||value.affine.length!==4
    ||!value.affine.every(r=>Array.isArray(r)&&r.length===4&&r.every(Number.isFinite))
    ||value.affine[3].some((v,i)=>v!==(i===3?1:0)))fail();
  const [[u,v,w],[p,q,r],[s,t,k]]=value.affine;
  const det=u*(q*k-r*t)-v*(p*k-r*s)+w*(p*t-q*s),scale=Math.hypot(u,p,s)*Math.hypot(v,q,t)*Math.hypot(w,r,k);
  if(!Number.isFinite(det)||!Number.isFinite(scale)||!(scale>0)||Math.abs(det)/scale<1e-8)fail();
}
function geometry(value){if(!exact(value,['version','sha256'])||value.version!=='ct-geometry/1.0'||!HASH.test(value.sha256))fail();}
export function reviewBinding(value){return canonical({id:value.id,reviewer_id:value.reviewer_id,case_id:value.case_id,
  slot:value.slot,protocol_version:value.protocol_version,source:value.source,geometry_identity:value.geometry_identity});}
export function validateReviewAssignment(input,ownerId,{detail=false,binding}={}){
  const value=detached(input),keys=['id','reviewer_id','slot','case_id','protocol_version','source','geometry_identity','review_mode',...flags];
  if(!exact(value,detail?[...keys,'source_current','source_unavailable_reason']:keys)||!positive(ownerId)||value.reviewer_id!==ownerId
    ||!UUID.test(value.id)||!['R1','R2'].includes(value.slot)||!positive(value.case_id)||typeof value.protocol_version!=='string'
    ||!value.protocol_version.trim()||value.protocol_version.length>128||value.review_mode!=='original_ct_only')fail();
  source(value.source);geometry(value.geometry_identity);unreleased(value);
  if(value.source.case_id!==value.case_id||binding!==undefined&&binding!==reviewBinding(value))fail();
  if(detail&&(typeof value.source_current!=='boolean'||(value.source_current?value.source_unavailable_reason!==null
    :typeof value.source_unavailable_reason!=='string'||!value.source_unavailable_reason.trim())))fail();
  return value;
}
export function validateReviewNote(input,assignment,ownerId,expected={}){
  const value=detached(input);
  if(!exact(value,['schema_version','assignment_id','owner_id','case_id','protocol_version','source','revision','notes','exists','status',...flags])
    ||value.schema_version!=='ct-review-note/0.1'||value.assignment_id!==assignment.id||value.owner_id!==ownerId
    ||value.case_id!==assignment.case_id||value.protocol_version!==assignment.protocol_version
    ||canonical(value.source)!==canonical(assignment.source)||!Number.isSafeInteger(value.revision)||value.revision<0||value.revision>2147483647
    ||typeof value.notes!=='string'||Array.from(value.notes).length>4000||typeof value.exists!=='boolean'
    ||value.exists!==(value.revision>0)||!value.exists&&value.notes!==''||value.status!=='unverified_draft'
    ||expected.revision!==undefined&&value.revision!==expected.revision||expected.notes!==undefined&&value.notes!==expected.notes)fail();
  unreleased(value);return value;
}
function path(id){if(typeof id!=='string'||!UUID.test(id))fail();return `/review-assignments/${id}`;}
export function createReviewAssignmentsApi(api){
  async function originalBytes(item,{signal,onProgress}={}){
    const controller=new AbortController(),cancel=()=>controller.abort();let exceeded=false;
    signal?.addEventListener('abort',cancel,{once:true});if(signal?.aborted)cancel();
    try{
      if(controller.signal.aborted)throw new DOMException('CT request cancelled.','AbortError');
      const r=await api.get(path(item.id)+'/source',{signal:controller.signal,timeout:120000,responseType:'arraybuffer',
        headers:{Accept:'application/gzip, application/octet-stream'},onDownloadProgress:event=>{
          if(event.loaded>512*1024*1024||event.total>512*1024*1024){exceeded=true;controller.abort();return;}
          onProgress?.({loaded:event.loaded,total:event.total||null});
        }});
      if(controller.signal.aborted)throw new DOMException('CT request cancelled.','AbortError');
      if(r.status!==200||!(r.data instanceof ArrayBuffer)||r.data.byteLength===0||r.data.byteLength>512*1024*1024
        ||/json|html|text\//i.test(r.headers?.['content-type']||''))fail();
      return r.data;
    }catch(error){
      if(exceeded)throw new Error('Original CT exceeds the browser transfer limit.');
      if(error.response?.data instanceof ArrayBuffer){
        try{const body=JSON.parse(new TextDecoder().decode(error.response.data));if(typeof body.detail==='string')error.message=body.detail;}catch{/* retain HTTP error */}
      }
      throw error;
    }finally{signal?.removeEventListener('abort',cancel);}
  }
  return {
  async list(ownerId,{signal}={}){
    const {data,status}=await api.get('/review-assignments',{signal,timeout:60000,params:{limit:50,offset:0}});
    if(status!==200||!exact(data,['items','limit','offset','next_offset','offset_limit_reached',...flags])||data.limit!==50||data.offset!==0
      ||!Array.isArray(data.items)||data.items.length>50||![null,50].includes(data.next_offset)||data.offset_limit_reached!==false)fail();
    unreleased(data);const items=data.items.map(row=>validateReviewAssignment(row,ownerId));
    if(new Set(items.map(row=>row.id)).size!==items.length)fail();
    return {...data,items};
  },
  async detail(item,ownerId,{signal}={}){
    const r=await api.get(path(item.id),{signal,timeout:60000});if(r.status!==200)fail();
    return validateReviewAssignment(r.data,ownerId,{detail:true,binding:reviewBinding(item)});
  },
  async note(item,ownerId,{signal}={}){
    const r=await api.get(path(item.id)+'/draft',{signal,timeout:60000});if(r.status!==200)fail();return validateReviewNote(r.data,item,ownerId);
  },
  async save(item,ownerId,notes,revision,{signal}={}){
    if(typeof notes!=='string'||Array.from(notes).length>4000||!Number.isSafeInteger(revision)||revision<0||revision>=2147483647)fail();
    const r=await api.put(path(item.id)+'/draft',{notes,expected_revision:revision,clinical_gate_authorized:false,training_release_authorized:false},{signal,timeout:60000});
    if(r.status!==(revision===0?201:200))fail();return validateReviewNote(r.data,item,ownerId,{revision:revision+1,notes});
  },
  async download(item,{signal}={}){
    const data=await originalBytes(item,{signal});
    const hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',data)),b=>b.toString(16).padStart(2,'0')).join('');
    if(hash!==item.source.source_sha256||signal?.aborted)fail();
    const bytes=new Uint8Array(data),gzip=bytes[0]===31&&bytes[1]===139;
    return {blob:new Blob([data],{type:'application/octet-stream'}),filename:`original-ct-${item.case_id}.nii${gzip?'.gz':''}`};
  },
  // Bytes remain untrusted until the dedicated CT worker verifies hash/geometry.
  loadOriginalCt:originalBytes,
  async preview(caseId,{signal}={}){
    if(!positive(caseId))fail();const r=await api.get('/review-studies/source',{signal,timeout:60000,params:{case_id:caseId}}),v=r.data;
    if(r.status!==200||!exact(v,['case_id','source','geometry_identity',...flags])||v.case_id!==caseId)fail();
    source(v.source);geometry(v.geometry_identity);unreleased(v);if(v.source.case_id!==caseId)fail();return detached(v);
  },
  async assign(body,{signal}={}){
    const r=await api.post('/review-studies',body,{signal,timeout:60000}),v=r.data;
    if(r.status!==201||!exact(v,['id','case_id','protocol_version','source','assignments',...flags])||!UUID.test(v.id)
      ||v.case_id!==body.case_id||v.protocol_version!==body.protocol_version||!Array.isArray(v.assignments)||v.assignments.length!==2)fail();
    source(v.source);unreleased(v);if(v.source.case_id!==body.case_id||v.source.source_sha256!==body.expected_ct_sha256)fail();
    for(const [i,slot] of ['R1','R2'].entries())if(!exact(v.assignments[i],['id','slot','reviewer_id'])||!UUID.test(v.assignments[i].id)
      ||v.assignments[i].slot!==slot||v.assignments[i].reviewer_id!==body[slot==='R1'?'r1_user_id':'r2_user_id'])fail();
    if(v.assignments[0].id===v.assignments[1].id)fail();return detached(v);
  },
};}
