import {validateAdjudicationDetail,canonical} from '../api/review-adjudications.js';
import {prepareOriginalCt} from './ct-review-loader.js';
import {volumeBudget} from './volume-geometry.js';

export const adjudicationCtBinding=item=>canonical({id:item.id,reviewer_id:item.reviewer_id,case_id:item.case_id,
  source:item.source,protocol_version:item.protocol_version,parents:item.parents.map(p=>p.record_sha256)});

export async function loadAdjudicationCt(api,item,owner,{signal,onPhase=()=>{},onProgress}={}){
  if(!signal||typeof signal.addEventListener!=='function')throw new TypeError('A caller-owned AbortSignal is required.');
  if(!globalThis.isSecureContext||!crypto?.subtle)throw new Error('CT identity verification requires HTTPS or localhost.');
  validateAdjudicationDetail(item,item.id,owner);volumeBudget(item.source.shape,globalThis.navigator?.deviceMemory||8);
  const token=localStorage.getItem('vascuai_token'),binding=adjudicationCtBinding(item);
  const current=()=>{if(signal.aborted||!token||token!==localStorage.getItem('vascuai_token'))throw new Error('Adjudication CT session changed or cancelled.');};
  const fresh=async()=>{
    current();const next=await api.detail(item.id,owner,{signal});current();
    validateAdjudicationDetail(next,item.id,owner);
    if(!next.source_current||adjudicationCtBinding(next)!==binding)throw new Error('Adjudication source, parents or access changed. No CT displayed.');
  };
  onPhase('Verifying third-reader CT access and frozen parents…');await fresh();
  onPhase('Downloading original CT only…');const ct=await api.loadOriginalCt(item,owner,{signal,onProgress});current();
  onPhase('Checking CT checksum and native geometry…');const packet=await prepareOriginalCt(ct,item.source,{signal});current();
  await fresh();return packet;
}
