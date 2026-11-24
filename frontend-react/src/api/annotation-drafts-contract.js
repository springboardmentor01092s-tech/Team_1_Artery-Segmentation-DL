import { validateAnnotationSource, validateAnnotationDraft, MAX_ANNOTATION_DRAFT_BYTES } from '../lib/annotation-draft.js';

const UUID=/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i;
const HASH=/^[a-f0-9]{64}$/;
const exact=(value,keys)=>value && typeof value==='object' && !Array.isArray(value)
  && Object.keys(value).length===keys.length && keys.every(key=>Object.hasOwn(value,key));
const integer=value=>Number.isSafeInteger(value)&&value>0;
const date=value=>typeof value==='string' && value.includes('T') && Number.isFinite(Date.parse(value));
const fail=()=>{throw new Error('Unexpected private annotation response. No saved draft was applied.');};
const canonical=value=>JSON.stringify(value,(_,item)=>item && typeof item==='object' && !Array.isArray(item)
  ? Object.fromEntries(Object.keys(item).sort().map(key=>[key,item[key]])):item);

function base(context) {
  validateAnnotationSource(context.source);
  if (!integer(context.ownerId) || context.source.case_id>2147483647) fail();
  return `/cases/${context.source.case_id}/annotation-drafts`;
}
function path(context,id) {
  if (typeof id!=='string' || !UUID.test(id)) fail();
  return `${base(context)}/${id}`;
}
export function annotationBinding(envelope) {
  return canonical({patient_id:envelope.patient_id,source:envelope.document.source,
    geometry_identity:envelope.geometry_identity,segmentation_provenance:envelope.segmentation_provenance});
}
export function annotationDocumentSnapshot(document,source) {
  validateAnnotationDraft(document,source);
  const content=JSON.stringify(document);
  if(new TextEncoder().encode(content).byteLength>MAX_ANNOTATION_DRAFT_BYTES) fail();
  const snapshot=JSON.parse(content);validateAnnotationDraft(snapshot,source);return snapshot;
}
export function validateAnnotationResponse(input,context,expected={}) {
  base(context);
  const value=JSON.parse(JSON.stringify(input));
  if (!exact(value,['id','patient_id','case_id','owner_id','revision','status','source_current','source_unavailable_reason',
    'geometry_identity','segmentation_provenance','document','clinical_gate_authorized','training_release_authorized','created_at','updated_at'])
      || typeof value.id!=='string' || !UUID.test(value.id) || !integer(value.patient_id) || !integer(value.revision)
      || value.case_id!==context.source.case_id || value.owner_id!==context.ownerId
      || value.status!=='unverified_server_draft' || typeof value.source_current!=='boolean'
      || value.clinical_gate_authorized!==false || value.training_release_authorized!==false
      || !date(value.created_at) || !date(value.updated_at)
      || (value.source_current ? value.source_unavailable_reason!==null
        : typeof value.source_unavailable_reason!=='string' || !value.source_unavailable_reason.trim())) fail();
  validateAnnotationDraft(value.document,context.source);
  const geometry=value.geometry_identity,provenance=value.segmentation_provenance;
  if (!exact(geometry,['version','sha256']) || geometry.version!=='ct-geometry/1.0' || typeof geometry.sha256!=='string' || !HASH.test(geometry.sha256)
      || !exact(provenance,['segmentation_result_id','checkpoint_sha256','mask_sha256','probabilities_sha256','threshold'])
      || provenance.segmentation_result_id!==context.source.segmentation_result_id
      || ['checkpoint_sha256','mask_sha256','probabilities_sha256'].some(key=>typeof provenance[key]!=='string'||!HASH.test(provenance[key]))
      || typeof provenance.threshold!=='number' || !Number.isFinite(provenance.threshold) || provenance.threshold<0 || provenance.threshold>1
      || context.checkpointSha256!==undefined && context.checkpointSha256!==provenance.checkpoint_sha256
      || expected.id!==undefined && value.id!==expected.id
      || expected.revision!==undefined && value.revision!==expected.revision
      || expected.binding!==undefined && annotationBinding(value)!==expected.binding
      || expected.document!==undefined && canonical(value.document)!==canonical(expected.document)) fail();
  return value;
}
function validateIndex(value,context,offset,limit) {
  if (!exact(value,['items','limit','offset','next_offset','offset_limit_reached']) || value.limit!==limit || value.offset!==offset
      || !Array.isArray(value.items) || value.items.length>limit || typeof value.offset_limit_reached!=='boolean'
      || value.next_offset!==null && (value.next_offset!==offset+limit || value.next_offset>1_000_000 || value.items.length!==limit)
      || value.offset_limit_reached && (value.next_offset!==null || offset+limit<=1_000_000)) fail();
  const ids=new Set();
  for(const row of value.items) {
    if (!exact(row,['id','case_id','owner_id','revision','segmentation_result_id','source_sha256','status','updated_at',
      'clinical_gate_authorized','training_release_authorized']) || typeof row.id!=='string' || !UUID.test(row.id) || ids.has(row.id)
        || row.case_id!==context.source.case_id || row.owner_id!==context.ownerId || !integer(row.revision)
        || row.source_sha256!==context.source.source_sha256 || row.segmentation_result_id!==context.source.segmentation_result_id
        || row.status!=='unverified_server_draft' || row.clinical_gate_authorized!==false || row.training_release_authorized!==false
        || !date(row.updated_at)) fail();
    ids.add(row.id);
  }
  return value;
}
export function createAnnotationDraftApi(api) {
  return {
    async list(context,offset=0,{signal}={}) {
      const url=base(context),limit=20;
      if(!Number.isSafeInteger(offset)||offset<0||offset>1_000_000) fail();
      const response=await api.get(url,{signal,timeout:60000,params:{segmentation_result_id:context.source.segmentation_result_id,limit,offset}});
      if(response.status!==200) fail();
      return validateIndex(JSON.parse(JSON.stringify(response.data)),context,offset,limit);
    },
    async read(context,id,{signal,binding}={}) {
      const response=await api.get(path(context,id),{signal,timeout:60000});
      if(response.status!==200) fail();
      return validateAnnotationResponse(response.data,context,{id,binding});
    },
    async save(context,document,current=null,{signal}={}) {
      const snapshot=annotationDocumentSnapshot(document,context.source),url=current?path(context,current.id):base(context);
      if(current && (!integer(current.revision)||current.revision>=2147483647)) fail();
      const body=current?{document:snapshot,expected_revision:current.revision}:{document:snapshot};
      if(new TextEncoder().encode(JSON.stringify(body)).byteLength>MAX_ANNOTATION_DRAFT_BYTES) fail();
      const response=await (current?api.put(url,body,{signal,timeout:60000}):api.post(url,body,{signal,timeout:60000}));
      if(response.status!==(current?200:201)) fail();
      const value=validateAnnotationResponse(response.data,context,{id:current?.id,revision:current?current.revision+1:1,
        binding:current?.binding,document:snapshot});
      if(!value.source_current) fail();
      return value;
    },
  };
}
