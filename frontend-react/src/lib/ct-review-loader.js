import {volumeBudget} from './volume-geometry.js';
import {reviewBinding,validateReviewAssignment} from '../api/review-assignments-contract.js';

export function prepareOriginalCt(ct,source,{signal}={}){
  if(!signal||signal.aborted)return Promise.reject(new DOMException('CT viewer cancelled.','AbortError'));
  return new Promise((resolve,reject)=>{
    const worker=new Worker(new URL('../workers/ct-review.worker.js',import.meta.url),{type:'module'});
    let settled=false;
    const finish=(error,data)=>{
      if(settled)return;settled=true;signal.removeEventListener('abort',abort);worker.terminate();
      if(error)reject(error);else resolve(data);
    };
    const abort=()=>finish(new DOMException('CT viewer cancelled.','AbortError'));
    signal.addEventListener('abort',abort,{once:true});
    worker.onmessage=({data})=>finish(data.error?new Error(data.error):null,data);
    worker.onerror=()=>finish(new Error('Original CT decoding failed. Use the verified download.'));
    try{worker.postMessage({ct,source},[ct]);}catch(error){finish(error);}
  });
}

export async function loadAssignedCt(api,item,ownerId,{signal,onPhase=()=>{},onProgress}={}){
  if(!signal||typeof signal.addEventListener!=='function')throw new TypeError('A caller-owned AbortSignal is required.');
  if(signal.aborted)throw new DOMException('CT viewer cancelled.','AbortError');
  if(!globalThis.isSecureContext||!globalThis.crypto?.subtle)throw new Error('CT identity verification requires HTTPS or localhost.');
  validateReviewAssignment(item,ownerId,{detail:true});
  volumeBudget(item.source.shape,globalThis.navigator?.deviceMemory||8);
  const binding=reviewBinding(item),token=localStorage.getItem('vascuai_token');
  const current=()=>{
    if(signal.aborted)throw new DOMException('CT viewer cancelled.','AbortError');
    if(token!==localStorage.getItem('vascuai_token'))throw new Error('Your session changed. Reopen the assigned CT viewer after signing in.');
  };
  const verify=async()=>{
    current();const next=await api.detail(item,ownerId,{signal});current();
    if(!next.source_current||reviewBinding(next)!==binding)throw new Error('The original CT assignment changed or is unavailable. No image was displayed.');
  };
  onPhase('Verifying original CT assignment…');await verify();
  onPhase('Downloading original CT only…');
  const ct=await api.loadOriginalCt(item,{signal,onProgress});current();
  onPhase('Checking CT checksum and native geometry…');
  const packet=await prepareOriginalCt(ct,item.source,{signal});current();
  await verify();return packet;
}
