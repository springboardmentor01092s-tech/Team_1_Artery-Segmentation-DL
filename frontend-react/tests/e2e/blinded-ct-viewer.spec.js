import {test,expect} from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import {createHash} from 'node:crypto';
import {gzipSync} from 'node:zlib';
import {installApi} from './fixtures';
import {syntheticNifti} from './nifti-fixture';
const id='11111111-1111-4111-8111-111111111111';
async function setup(page,options={}){
  await installApi(page,{role:'Clinician'});
  const affine=options.permuted?[[0,-1.2,0,24],[-.7,0,0,-13],[0,0,2.5,42],[0,0,0,1]]
    :options.oblique?[[.7,.1,0,24],[0,1.2,0,-13],[0,0,2.5,42],[0,0,0,1]]:[[-.7,0,0,24],[0,1.2,0,-13],[0,0,2.5,42],[0,0,0,1]];
  const ct=gzipSync(syntheticNifti({affine})),source={case_id:1,source_sha256:createHash('sha256').update(ct).digest('hex'),shape:[12,10,8],affine:structuredClone(affine),units:'mm'};
  if(options.badHash)source.source_sha256='f'.repeat(64);if(options.badGeometry)source.affine[0][3]+=1;
  if(options.largeSource)source.shape=[512,512,275]; // Metadata-only resource refusal; no large array is generated.
  const flags={clinical_gate_authorized:false,training_release_authorized:false,reader_independence_verified:false,qualification_verified:false};
  const item={id,reviewer_id:1,slot:'R1',case_id:1,protocol_version:'synthetic-unapproved',source,
    geometry_identity:{version:'ct-geometry/1.0',sha256:'b'.repeat(64)},review_mode:'original_ct_only',...flags};
  const state={stale:false,hold:options.slow,requests:[],bytes:0,details:0,annotation:null,annotationRevision:0,writes:[],submission:null,amendments:[]};
  page.on('request',r=>{if(new URL(r.url()).pathname.startsWith('/api/v1/'))state.requests.push(new URL(r.url()).pathname);});
  await page.route('**/api/v1/review-assignments**',async route=>{
    const req=route.request(),p=new URL(req.url()).pathname;
    if(p.endsWith('/review-assignments'))return route.fulfill({json:{items:[item],limit:50,offset:0,next_offset:null,offset_limit_reached:false,...flags}});
    if(p.endsWith('/source')){
      state.bytes++;if(state.hold){state.pending=true;await new Promise(resolve=>{state.release=resolve;});}
      return route.fulfill({contentType:'application/gzip',body:ct});
    }
    if(p.endsWith('/annotation-draft')){
      if(req.method()==='PUT'){
        if(state.submission)return route.fulfill({status:409,json:{detail:'Submitted annotation is immutable'}});
        const body=req.postDataJSON();state.writes.push(body);
        if(body.expected_revision!==state.annotationRevision)return route.fulfill({status:409,json:{detail:'Annotation revision conflict'}});
        state.annotation=body.document;state.annotationRevision++;
      }
      return route.fulfill({status:req.method()==='PUT'&&state.annotationRevision===1?201:200,json:{assignment_id:id,owner_id:1,case_id:1,
        protocol_version:item.protocol_version,source,geometry_identity:item.geometry_identity,revision:state.annotationRevision,
        document:state.annotation,exists:state.annotationRevision>0,content_sha256:state.annotation?'c'.repeat(64):null,status:'unverified_draft',
        source_current:!state.stale,source_unavailable_reason:state.stale?'changed':null,submitted:Boolean(state.submission),...flags}});
    }
    if(p.endsWith('/submit')){
      const body=req.postDataJSON();
      if(body.expected_revision!==state.annotationRevision||body.expected_document_sha256!=='c'.repeat(64))return route.fulfill({status:409,json:{detail:'Revision conflict'}});
      state.submission={schema_version:'independent-review-submission/0.1',id:'33333333-3333-4333-8333-333333333333',assignment_id:id,
        reviewer_id:1,case_id:1,source,protocol_version:item.protocol_version,annotation_revision:state.annotationRevision,
        document_sha256:'c'.repeat(64),document:state.annotation,submitted_at:'2026-11-23T00:00:00Z',...flags};
      return route.fulfill({status:201,json:{submission:state.submission,record_sha256:'d'.repeat(64),...flags}});
    }
    if(p.endsWith('/amendments')){
      if(req.method()==='POST'){
        const body=req.postDataJSON(),revision=state.amendments.length+1,previous=state.amendments.at(-1)||null;
        if(!state.submission||body.expected_submission_sha256!=='d'.repeat(64)||body.expected_revision!==state.amendments.length
          ||body.expected_previous_sha256!==(previous?.record_sha256??null))return route.fulfill({status:409,json:{detail:'Amendment conflict'}});
        const amendment={schema_version:'review-submission-amendment/0.1',id:`44444444-4444-4444-8444-${String(revision).padStart(12,'0')}`,
          assignment_id:id,submission_id:state.submission.id,reviewer_id:1,revision,previous_id:previous?.id??null,
          previous_sha256:previous?.record_sha256??null,parent_submission_sha256:'d'.repeat(64),parent_annotation_revision:state.annotationRevision,
          source,geometry_identity:item.geometry_identity,protocol_version:item.protocol_version,reason:body.reason,
          document_sha256:'e'.repeat(64),document:body.document,status:'unverified_addendum_original_submission_unchanged',
          recorded_at:'2026-11-24T00:00:00Z',...flags};
        const row={id:amendment.id,revision,previous_id:amendment.previous_id,previous_sha256:amendment.previous_sha256,
          parent_submission_sha256:amendment.parent_submission_sha256,document_sha256:amendment.document_sha256,
          record_sha256:String(revision).repeat(64),amendment,created_at:amendment.recorded_at};state.amendments.push(row);
        return route.fulfill({status:201,json:{...row,...flags}});
      }
      return route.fulfill({json:{schema_version:'review-amendment-history/0.1',assignment_id:id,
        submission_id:state.submission?.id||null,submission_sha256:state.submission?'d'.repeat(64):null,source_current:!state.stale,
        items:state.amendments,revision:state.amendments.length,latest_sha256:state.amendments.at(-1)?.record_sha256??null,
        max_amendments:100,...flags}});
    }
    if(p.endsWith('/submission'))return route.fulfill({json:{exists:Boolean(state.submission),submission:state.submission,record_sha256:state.submission?'d'.repeat(64):null,source_current:true,...flags}});
    if(p.endsWith('/draft'))return route.fulfill({json:{schema_version:'ct-review-note/0.1',assignment_id:id,owner_id:1,case_id:1,source,
      protocol_version:item.protocol_version,revision:0,notes:'',exists:false,status:'unverified_draft',...flags}});
    state.details++;return route.fulfill({json:{...item,source_current:!state.stale,source_unavailable_reason:state.stale?'CT changed':null}});
  });
  await page.goto('/review-assignments');await page.getByLabel('Assignment',{exact:true}).selectOption(id);
  await page.getByRole('button',{name:'Load selected assignment',exact:true}).click();
  await expect(page.getByLabel('Private unverified preparation notes')).toBeVisible();
  state.requests=[];
  await page.getByRole('button',{name:'Open blinded original CT viewer',exact:true}).click();
  return state;
}
const ready=page=>expect(page.getByTestId('ct-only-ready')).toHaveText('Verified original CT · 1 volume · no overlays.',{timeout:30000});

test('large CT refusal retains source-bound manual worksheet without raising the viewer budget',async({page})=>{
  const state=await setup(page,{largeSource:true});
  await expect(page.getByRole('region',{name:'Blinded original CT viewer'}).getByRole('alert')).toContainText(/limit|budget/);
  expect(state.bytes).toBe(0);await expect(page.getByTestId('ct-only-ready')).toHaveCount(0);
  const formal=page.getByRole('region',{name:'Formal unverified lesion annotation'});
  await expect(formal).toBeVisible({timeout:5000});await formal.getByRole('button',{name:'Add manual lesion row',exact:true}).click();
  await expect(formal.getByRole('button',{name:'Capture Lesion center',exact:true})).toBeDisabled();
  await formal.getByLabel('Manual Lesion center native IJK',{exact:true}).fill('2, 3, 1');
  await formal.getByRole('button',{name:'Apply manual Lesion center',exact:true}).click();
  await expect(formal.getByLabel('Lesion center native IJK',{exact:true})).toHaveText('2, 3, 1');
  await formal.getByRole('button',{name:'Save formal unverified draft',exact:true}).click();
  await expect(formal.getByRole('status',{name:'Formal worksheet status',exact:true})).toContainText('saved at revision 1');
  expect(state.writes[0].document.lesions[0].minimum_lumen_diameter_mm).toBe(null);
  expect(state.writes[0].document.clinical_gate_authorized).toBe(false);
  await formal.getByLabel('Manual Lesion center native IJK',{exact:true}).fill('512, 0, 0');
  await formal.getByRole('button',{name:'Apply manual Lesion center',exact:true}).click();
  await expect(formal.getByRole('alert')).toContainText('outside the original native CT grid');
  await expect(formal.getByLabel('Lesion center native IJK',{exact:true})).toHaveText('2, 3, 1');
});
test('CT-only viewer renders slices, windowing, zoom/pan/reset with no AI routes or overlay controls',async({page})=>{
  const errors=[];page.on('pageerror',e=>errors.push(e.message));const state=await setup(page);await ready(page);
  const viewer=page.getByRole('region',{name:'Blinded original CT viewer'}),canvas=viewer.getByRole('img',{name:'Original CT slices without overlays'});
  await expect(canvas).toBeVisible();expect(state.bytes).toBe(1);
  expect(state.requests.every(p=>p.startsWith(`/api/v1/review-assignments/${id}`))).toBe(true);
  await viewer.getByLabel('Axial CT slice',{exact:true}).fill('3');await viewer.getByLabel('Coronal CT slice',{exact:true}).fill('4');
  await viewer.getByLabel('Sagittal CT slice',{exact:true}).fill('9');
  await expect(viewer.getByText('Native IJK:',{exact:false})).toContainText('2, 4, 3');
  const before=await canvas.screenshot();await viewer.getByLabel('CT window width',{exact:true}).fill('300');
  await viewer.getByLabel('CT window level',{exact:true}).fill('500');const after=await canvas.screenshot();expect(before.equals(after)).toBe(false);
  for(const view of ['axial','coronal','sagittal','slices'])await viewer.getByLabel('CT view',{exact:true}).selectOption(view);
  for(const label of ['Zoom CT in','Zoom CT out','Pan CT left','Pan CT right','Pan CT up','Pan CT down','Reset CT display'])await viewer.getByRole('button',{name:label,exact:true}).click();
  await expect(viewer.getByLabel('Show segmentation',{exact:true})).toHaveCount(0);await expect(viewer.getByText('Prepare a local lesion review draft',{exact:true})).toHaveCount(0);
  const violations=await new AxeBuilder({page}).include('.volume-viewer').withTags(['wcag2a','wcag2aa']).analyze();expect(violations.violations).toEqual([]);
  await page.screenshot({path:test.info().outputPath('blinded-original-ct.png'),fullPage:true});
  const handle=await canvas.elementHandle();await viewer.getByRole('button',{name:'Close original CT viewer',exact:true}).click();
  await expect(canvas).toHaveCount(0);await expect.poll(()=>handle.evaluate(e=>e.getContext('webgl2').isContextLost())).toBe(true);await handle.dispose();
  await expect(page.getByRole('button',{name:'Open blinded original CT viewer',exact:true})).toBeFocused();expect(errors).toEqual([]);
});
test('permuted CT crosshair uses native IJK rather than anatomical slider order',async({page})=>{
  await setup(page,{permuted:true});await ready(page);const viewer=page.getByRole('region',{name:'Blinded original CT viewer'});
  await viewer.getByLabel('Sagittal CT slice',{exact:true}).fill('5');await viewer.getByLabel('Coronal CT slice',{exact:true}).fill('9');await viewer.getByLabel('Axial CT slice',{exact:true}).fill('3');
  await expect(viewer.getByText('Native IJK:',{exact:false})).toContainText('2, 4, 3');
  await expect(viewer.getByText('Crosshair RAS:',{exact:false})).toContainText('19.20, -14.40, 49.50');
});
for(const [option,message] of [['badHash','checksum mismatch'],['badGeometry','geometry does not match'],['oblique','Oblique or sheared']])test(`CT viewer rejects ${option} with no rendered image`,async({page})=>{
  const state=await setup(page,{[option]:true});const viewer=page.getByRole('region',{name:'Blinded original CT viewer'});
  await expect(viewer.getByRole('alert')).toContainText(message);await expect(page.getByTestId('ct-only-ready')).toHaveCount(0);
  await expect(page.getByRole('region',{name:'Formal unverified lesion annotation'})).toHaveCount(0);
  await expect(viewer.getByRole('img')).toBeHidden();expect(state.requests.some(p=>/segmentations|predictions|evaluations|stenosis/.test(p))).toBe(false);
});
test('freshness failure clears existing CT pixels rather than displaying a replacement',async({page})=>{
  const state=await setup(page);await ready(page);state.stale=true;
  await page.evaluate(()=>window.dispatchEvent(new Event('focus')));
  const viewer=page.getByRole('region',{name:'Blinded original CT viewer'});
  await expect(viewer.getByRole('alert')).toContainText('unavailable or changed');await expect(viewer.getByRole('img')).toBeHidden();expect(state.bytes).toBe(1);
});
test('logout during CT download cannot restore the old viewer after login',async({page})=>{
  const state=await setup(page,{slow:true});await expect.poll(()=>state.pending).toBe(true);
  await page.getByRole('button',{name:'Sign out',exact:true}).click();await expect(page).toHaveURL(/\/login$/);state.release();
  await page.getByLabel('Email address',{exact:true}).fill('alex@example.test');await page.getByLabel('Password',{exact:true}).fill('synthetic-only');
  await page.getByRole('button',{name:'Sign in to workspace',exact:true}).click();await expect(page).not.toHaveURL(/\/login$/);
  await page.goto('/review-assignments');await expect(page.getByRole('region',{name:'Blinded original CT viewer'})).toHaveCount(0);
});
test('closing during CT decoding/download ignores completion and releases the session',async({page})=>{
  const state=await setup(page,{slow:true});await expect.poll(()=>state.pending).toBe(true);
  await page.getByRole('button',{name:'Close original CT viewer',exact:true}).click();state.release();
  await expect(page.getByTestId('ct-only-ready')).toHaveCount(0);await expect(page.getByRole('region',{name:'Blinded original CT viewer'})).toHaveCount(0);
});

test('formal worksheet captures seven native points, preserves nulls and requires explicit 409 reload',async({page})=>{
  const state=await setup(page);await ready(page);const panel=page.getByRole('region',{name:'Formal unverified lesion annotation'});
  await panel.getByRole('button',{name:'Add manual lesion row',exact:true}).click();
  for(const name of ['Lesion center','Proximal boundary','Distal boundary','Minimum caliper start','Minimum caliper end','Reference caliper start','Reference caliper end']){
    await panel.getByRole('button',{name:`Capture ${name}`,exact:true}).click();
    await expect(panel.getByLabel(`${name} native IJK`,{exact:true})).not.toHaveText('Unavailable');
  }
  await panel.getByLabel('Minimum lumen diameter (mm, manual)',{exact:true}).fill('0');
  await panel.getByLabel('Measurement method',{exact:true}).fill('Synthetic software-only manual entry');
  await panel.getByLabel('Measurement evidence',{exact:true}).fill('Synthetic fixture, not expert ground truth');
  await panel.getByRole('button',{name:'Save formal unverified draft',exact:true}).click();
  await expect(panel.getByRole('status',{name:'Formal worksheet status',exact:true})).toContainText('saved at revision 1');
  expect(state.annotation.lesions[0].minimum_lumen_diameter_mm).toBe(0);
  expect(state.annotation.lesions[0].percentage_narrowing).toBeNull();expect(state.annotation.lesions[0].severity_category).toBeNull();
  const waiting=page.waitForEvent('download');await panel.getByRole('button',{name:'Download unverified worksheet JSON',exact:true}).click();
  const download=await waiting;const buffer=await (await import('node:fs/promises')).readFile(await download.path());
  await panel.getByLabel('Lesion notes',{exact:true}).fill('unsaved notes');
  await panel.getByLabel('Restore source-bound worksheet JSON',{exact:true}).setInputFiles({name:'synthetic-reader.json',mimeType:'application/json',buffer});
  await expect(panel.getByLabel('Lesion notes',{exact:true})).toHaveValue('');expect(state.writes).toHaveLength(1);
  state.annotationRevision=2;state.annotation.lesions[0].notes='other tab revision';
  await panel.getByLabel('Lesion notes',{exact:true}).fill('keep local notes');
  await panel.getByRole('button',{name:'Save formal unverified draft',exact:true}).click();
  await expect(panel.getByLabel('Lesion notes',{exact:true})).toHaveValue('keep local notes');
  await expect(panel.getByRole('button',{name:'Save formal unverified draft',exact:true})).toBeDisabled();
  await panel.getByRole('button',{name:'Reload latest and replace worksheet',exact:true}).click();
  await expect(panel.getByLabel('Lesion notes',{exact:true})).toHaveValue('other tab revision');
});

test('explicit submission freezes the retained worksheet and remains read-only after reopening',async({page})=>{
  const state=await setup(page);await ready(page);let panel=page.getByRole('region',{name:'Formal unverified lesion annotation'});
  await expect(panel.getByRole('button',{name:'Save formal unverified draft',exact:true})).toBeEnabled();
  await panel.getByRole('button',{name:'Save formal unverified draft',exact:true}).click();
  await expect(panel.getByRole('status',{name:'Formal worksheet status',exact:true})).toContainText('saved at revision 1');
  await panel.getByRole('checkbox',{name:/I explicitly freeze/}).check();
  await panel.getByRole('button',{name:'Submit immutable unverified review',exact:true}).click();
  await expect(panel.getByText('This submitted review is immutable.',{exact:false})).toBeVisible();
  await expect(panel.getByRole('button',{name:'Save formal unverified draft',exact:true})).toBeDisabled();
  await expect(panel.getByLabel('Case assessment',{exact:true})).toBeDisabled();
  await expect(panel.getByLabel('Restore source-bound worksheet JSON',{exact:true})).toBeDisabled();
  expect(state.submission.clinical_gate_authorized).toBe(false);expect(state.submission.training_release_authorized).toBe(false);
  await page.getByRole('button',{name:'Close original CT viewer',exact:true}).click();
  await page.getByRole('button',{name:'Open blinded original CT viewer',exact:true}).click();await ready(page);
  panel=page.getByRole('region',{name:'Formal unverified lesion annotation'});
  await expect(panel.getByText('This submitted review is immutable.',{exact:false})).toBeVisible();
  await expect(panel.getByRole('button',{name:'Save formal unverified draft',exact:true})).toBeDisabled();
});

test('post-submission amendment is a separate hash-linked record and cannot edit the frozen review',async({page})=>{
  const state=await setup(page);await ready(page);const panel=page.getByRole('region',{name:'Formal unverified lesion annotation'});
  await panel.getByRole('button',{name:'Save formal unverified draft',exact:true}).click();
  await panel.getByRole('checkbox',{name:/I explicitly freeze/}).check();
  await panel.getByRole('button',{name:'Submit immutable unverified review',exact:true}).click();
  await expect(panel.getByRole('button',{name:'Start a separate unverified amendment',exact:true})).toBeEnabled();
  const original=structuredClone(state.submission);
  await panel.getByRole('button',{name:'Start a separate unverified amendment',exact:true}).click();
  await panel.getByLabel('Case unavailable reason',{exact:true}).fill('A separate synthetic software addendum; no clinical conclusion.');
  await panel.getByLabel('Reason for amendment',{exact:true}).fill('Corrected explanatory text for software workflow test.');
  await panel.getByRole('button',{name:'Save new immutable amendment',exact:true}).click();
  await expect(panel.getByRole('status',{name:'Formal worksheet status',exact:true})).toContainText('Separate amendment 1 was hash-linked');
  expect(state.submission).toEqual(original);expect(state.amendments).toHaveLength(1);
  expect(state.amendments[0].amendment.clinical_gate_authorized).toBe(false);
  expect(state.amendments[0].amendment.training_release_authorized).toBe(false);
  await expect(panel.getByLabel('My amendment history').getByText(/^Amendment 1 ·/)).toBeVisible();
});
