import {verifyOriginalCt} from '../lib/ct-review-volume.js';

self.onmessage=async({data})=>{
  try{
    if(!data||Object.keys(data).length!==2||!Object.hasOwn(data,'ct')||!Object.hasOwn(data,'source'))
      throw new Error('Only the original assigned CT is accepted by this viewer.');
    const result=await verifyOriginalCt(data.ct,data.source);
    self.postMessage(result,[result.ct]);
  }catch(error){self.postMessage({error:error.message||'Original CT verification failed.'});}
};
