import {VerifiedOriginalCtViewer} from './BlindedCtViewer';
import {adjudicationsApi} from '../api/review-adjudications';
import {adjudicationCtBinding,loadAdjudicationCt} from '../lib/adjudication-ct-loader';
const access={
  detail:async(item,owner,options)=>{
    const next=await adjudicationsApi.detail(item.id,owner,options);
    if(adjudicationCtBinding(next)!==adjudicationCtBinding(item))throw new Error('Third-reader source or frozen parents changed');
    return next;
  },
  load:(item,owner,options)=>loadAdjudicationCt(adjudicationsApi,item,owner,options),
};
export default function AdjudicationCtViewer(props){
  return <VerifiedOriginalCtViewer {...props} adjudication access={access}/>;
}
