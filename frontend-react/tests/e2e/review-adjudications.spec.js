import {test,expect} from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import {installApi} from './fixtures';
import {newReviewAnnotation} from '../../src/lib/review-annotation.js';
import {syntheticNifti} from './nifti-fixture.js';
import {inspectVolume} from '../../src/lib/volume-geometry.js';
import {createHash} from 'node:crypto';
const id='11111111-1111-4111-8111-111111111111',readerId='22222222-2222-4222-8222-222222222222';
async function setup(page,{admin=false,conflict=false,slow=false,ct=false}={}){
  await installApi(page,{role:admin?'Admin':'Clinician'});
  const source={case_id:1,source_sha256:'a'.repeat(64),shape:[12,10,8],affine:[[1,0,0,0],[0,2,0,0],[0,0,3,0],[0,0,0,1]],units:'mm'},flags={clinical_gate_authorized:false,training_release_authorized:false};
  let original;
  if(ct){original=syntheticNifti();const g=inspectVolume(original.buffer);Object.assign(source,{shape:g.shape,affine:g.affine,source_sha256:createHash('sha256').update(original).digest('hex')});}
  const item={id,reviewer_id:1,case_id:1,source,protocol_version:'synthetic-unapproved',source_current:true,current:null,history:[],...flags};
  item.parents=[1,2].map(n=>({record_sha256:String(n).repeat(64),submission:{schema_version:'independent-review-submission/0.1',assignment_id:readerId,reviewer_id:n,source,
    protocol_version:item.protocol_version,document:newReviewAnnotation({id:readerId,source,protocol_version:item.protocol_version}),...flags}}));
  const state={writes:[],pending:false,release:null,revoked:false,sourceRequests:0};
  await page.route(/\/api\/v1\/review-adjudic/,async route=>{
    const request=route.request(),path=new URL(request.url()).pathname;
    if(state.revoked)return route.fulfill({status:409,json:{detail:'Synthetic credential revoked'}});
    if(path.endsWith('/source')){state.sourceRequests++;return route.fulfill({contentType:'application/octet-stream',body:Buffer.from(original)});}
    if(path.endsWith('catalogue'))return route.fulfill({json:{studies:[],credentials:[],...flags}});
    if(path.endsWith('/review-adjudications'))return route.fulfill({json:{items:[{id,case_id:1,protocol_version:item.protocol_version}],next_offset:null,...flags}});
    if(request.method()==='PUT'){
      const body=request.postDataJSON();state.writes.push(body);
      if(conflict)return route.fulfill({status:409,json:{detail:'Synthetic revision conflict'}});
      item.current={record_sha256:'c'.repeat(64),document_sha256:'d'.repeat(64),...flags,record:{schema_version:'review-adjudication-version/0.1',assignment_id:id,
        reviewer_id:1,revision:1,document:body.document,status:'unverified_adjudication_draft',...flags}};
      item.history=[{revision:1,record_sha256:'c'.repeat(64),previous_sha256:null,final:false}];return route.fulfill({json:item.current});
    }
    if(request.method()==='POST'){
      state.writes.push(request.postDataJSON());item.current={...item.current,record_sha256:'e'.repeat(64),record:{...item.current.record,revision:2,status:'adjudicated_unverified'}};
      item.history.push({revision:2,record_sha256:'e'.repeat(64),previous_sha256:'c'.repeat(64),final:true});return route.fulfill({status:201,json:item.current});
    }
    if(slow){state.pending=true;await new Promise(resolve=>state.release=resolve);}
    return route.fulfill({json:item});
  });
  await page.goto('/review-adjudications');
  if(!admin){await page.getByLabel('Adjudication assignment',{exact:true}).selectOption(id);await page.getByRole('button',{name:'Load selected adjudication',exact:true}).click();}
  return state;
}
test('third-reader UI saves and freezes unverified adjudication without clinical output',async({page})=>{
  const state=await setup(page);await page.getByText('R1 frozen review',{exact:true}).click();await expect(page.getByText('R2 frozen review',{exact:true})).toBeVisible();
  await page.getByLabel('Outcome',{exact:true}).selectOption('unresolved');await page.getByLabel('Decision or unresolved reason',{exact:true}).fill('Parent reviews unassessed; qualified clinical interpretation remains unresolved.');
  await page.getByRole('button',{name:'Save adjudication revision',exact:true}).click();await expect(page.getByText('Unverified adjudication saved at revision 1.',{exact:true})).toBeVisible();
  await page.getByLabel('I reviewed the frozen source-bound records.',{exact:false}).check();await page.getByRole('button',{name:'Freeze unverified adjudication',exact:true}).click();
  await expect(page.getByText('Immutable adjudication recorded.',{exact:false})).toBeVisible();await expect(page.getByLabel('Outcome',{exact:true})).toBeDisabled();
  expect(state.writes[0].document.clinical_gate_authorized).toBe(false);expect(state.writes[1].expected_document_sha256).toBe('d'.repeat(64));
  const a11y=await new AxeBuilder({page}).include('main').withTags(['wcag2a','wcag2aa']).analyze();expect(a11y.violations).toEqual([]);
});
test('adjudication stale saves require explicit reload',async({page})=>{
  await setup(page,{conflict:true});await page.getByRole('button',{name:'Save adjudication revision',exact:true}).click();
  await expect(page.getByRole('button',{name:'Reload latest and replace my unsaved adjudication',exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'Save adjudication revision',exact:true})).toBeDisabled();
});
test('coordinator cannot self-certify missing reviewer credentials',async({page})=>{
  await setup(page,{admin:true});await expect(page.getByText('No verified reviewer credentials are registered.',{exact:false})).toBeVisible();
  await expect(page.getByRole('button',{name:'Assign after both reviews are frozen',exact:true})).toBeDisabled();
});
test('old-session adjudication cannot appear after logout',async({page})=>{
  const state=await setup(page,{slow:true});await expect.poll(()=>state.pending).toBe(true);
  await page.getByRole('button',{name:'Sign out',exact:true}).click();await expect(page).toHaveURL(/\/login$/);state.release();
  await expect(page.getByText('Frozen independent reviews',{exact:true})).toHaveCount(0);
});
test('local worksheet validation preserves editable input without pretending a revision conflict',async({page})=>{
  const state=await setup(page);const save=page.getByRole('button',{name:'Save adjudication revision',exact:true});
  await page.getByLabel('Decision or unresolved reason',{exact:true}).fill('');await save.click();
  await expect(page.getByRole('alert')).toContainText('Invalid source-bound adjudication document');await expect(save).toBeEnabled();
  expect(state.writes).toEqual([]);await page.getByLabel('Decision or unresolved reason',{exact:true}).fill('Synthetic correction; no clinical finding.');
  await save.click();await expect(page.getByText('Unverified adjudication saved at revision 1.',{exact:true})).toBeVisible();
});

test('third-reader CT is embedded without a reader worksheet and revoked access clears pixels',async({page})=>{
  const state=await setup(page,{ct:true});
  await page.getByRole('button',{name:'Open adjudication original CT viewer',exact:true}).click();
  const viewer=page.getByRole('region',{name:'Adjudication original CT viewer'});
  await expect(viewer.getByTestId('ct-only-ready')).toBeVisible();
  await viewer.getByLabel('Axial CT slice',{exact:true}).fill('2');
  // Negative native R axis: RAS index 6 is native i=11-6=5.
  await expect(viewer.getByText('Native IJK:',{exact:false})).toContainText('5, 5, 2');
  await expect(viewer.getByText('Crosshair RAS:',{exact:false})).toContainText('20.50, -7.00, 47.00');
  await expect(viewer.getByRole('region',{name:'Formal unverified lesion annotation'})).toHaveCount(0);
  expect(state.sourceRequests).toBe(1);expect(state.writes).toEqual([]);
  state.revoked=true;await page.evaluate(()=>window.dispatchEvent(new Event('focus')));
  await expect(viewer.getByRole('alert')).toContainText('CT access or source freshness could not be verified');
  await expect(viewer.getByRole('img',{name:'Original CT slices without overlays'})).toBeHidden();
});

test('same-window session change clears third-reader CT without needing a storage event',async({page})=>{
  await setup(page,{ct:true});await page.getByRole('button',{name:'Open adjudication original CT viewer',exact:true}).click();
  const viewer=page.getByRole('region',{name:'Adjudication original CT viewer'});await expect(viewer.getByTestId('ct-only-ready')).toBeVisible();
  await page.evaluate(()=>localStorage.setItem('vascuai_token','new-synthetic-session'));
  await expect(page.getByRole('alert')).toContainText('Your session changed');
  await expect(viewer).toHaveCount(0);
  await expect(page.getByText('Frozen independent reviews',{exact:true})).toHaveCount(0);
});
