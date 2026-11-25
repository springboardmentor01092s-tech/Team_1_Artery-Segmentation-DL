// UI regressions use explicit synthetic intercepts; the separate live runner
// exercises the same controls against actual FastAPI/disposable PostgreSQL.
import {test,expect} from '@playwright/test';
import {installApi} from './fixtures';
import {loadExperimentalFixture} from '../experimental-candidates-fixtures';
import {readFile} from 'node:fs/promises';

async function workspace(page) {
  await installApi(page);
  const fixture=await loadExperimentalFixture(),records=new Map();
  const state={stale:false,writes:[],readPending:false,holdRead:false};
  let sequence=0;
  const response=(doc,id,revision=1)=>({id,patient_id:1,case_id:1,owner_id:1,revision,status:'unverified_server_draft',
    source_current:true,source_unavailable_reason:null,geometry_identity:{version:'ct-geometry/1.0',sha256:'c'.repeat(64)},
    segmentation_provenance:{segmentation_result_id:fixture.segmentation.id,checkpoint_sha256:'a'.repeat(64),
      mask_sha256:'b'.repeat(64),probabilities_sha256:'d'.repeat(64),threshold:.5},document:structuredClone(doc),
    clinical_gate_authorized:false,training_release_authorized:false,created_at:'2026-11-23T00:00:00Z',updated_at:'2026-11-23T00:00:00Z'});
  await page.route('**/api/v1/cases/1/segmentations**',route=>{
    const path=new URL(route.request().url()).pathname;
    return path.endsWith('/segmentations')?route.fulfill({json:[{...fixture.segmentation,stale:state.stale}]}):
      route.fulfill({contentType:'application/gzip',body:path.endsWith('/source')?fixture.ctGzip:fixture.maskGzip});
  });
  await page.route('**/api/v1/cases/1/annotation-drafts**',async route=>{
    const req=route.request(),url=new URL(req.url()),id=url.pathname.split('/')[6],method=req.method();
    if(method==='POST') {
      state.writes.push(req.postDataJSON());
      const id=`44444444-4444-4444-8444-${String(++sequence).padStart(12,'0')}`;
      const value=response(req.postDataJSON().document,id);records.set(id,value);return route.fulfill({status:201,json:value});
    }
    if(!id) {
      const items=[...records.values()].map(value=>({id:value.id,case_id:1,owner_id:1,revision:value.revision,
        segmentation_result_id:fixture.segmentation.id,source_sha256:value.document.source.source_sha256,status:value.status,
        updated_at:value.updated_at,clinical_gate_authorized:false,training_release_authorized:false}));
      return route.fulfill({json:{items,limit:20,offset:0,next_offset:null,offset_limit_reached:false}});
    }
    if(!records.has(id))return route.fulfill({status:404,json:{detail:'Annotation draft not found'}});
    if(method==='PUT') {
      const body=req.postDataJSON();state.writes.push(body);
      if(body.expected_revision!==records.get(id).revision)return route.fulfill({status:409,json:{detail:'Annotation draft revision conflict'}});
      const value=response(body.document,id,body.expected_revision+1);records.set(id,value);return route.fulfill({json:value});
    }
    if(state.holdRead) {state.readPending=true;await new Promise(resolve=>{state.releaseRead=resolve;});}
    return route.fulfill({json:records.get(id)});
  });
  async function openViewer() {
    await page.goto('/cases/1/analysis');
    await page.getByRole('button',{name:`View CT + Segmentation for run ${fixture.segmentation.id}`}).click();
    await page.getByText('Prepare a local lesion review draft',{exact:true}).click();
    return page.getByLabel('Local lesion annotation draft',{exact:true});
  }
  return {fixture,records,state,openViewer,panel:await openViewer()};
}

test('private Save/Load survives logout/login while local JSON remains separate',async({page})=>{
  const controls=await workspace(page);let panel=controls.panel;
  await panel.getByLabel('Reviewer reference (unverified)').fill('synthetic persisted note');
  await panel.getByRole('button',{name:'Save private server draft',exact:true}).click();
  await expect(panel.getByRole('status')).toContainText('revision 1');
  const id=await panel.getByLabel('Server draft ID',{exact:true}).inputValue();
  expect(controls.records.get(id).clinical_gate_authorized).toBe(false);
  expect(controls.records.get(id).training_release_authorized).toBe(false);
  await page.getByRole('button',{name:'Sign out',exact:true}).click();
  await page.getByLabel('Email address',{exact:true}).fill('alex@example.test');
  await page.getByLabel('Password',{exact:true}).fill('synthetic-test-only');
  await page.getByRole('button',{name:'Sign in to workspace',exact:true}).click();
  await expect(page).not.toHaveURL(/\/login$/);
  panel=await controls.openViewer();
  await expect(panel.getByLabel('Reviewer reference (unverified)')).toHaveValue('');
  await panel.getByRole('button',{name:'Refresh my saved drafts',exact:true}).click();
  await panel.getByLabel('Saved private draft').selectOption(id);
  await panel.getByRole('button',{name:'Load selected server draft and replace local edits',exact:true}).click();
  await expect(panel.getByLabel('Reviewer reference (unverified)')).toHaveValue('synthetic persisted note');
  const waiting=page.waitForEvent('download');
  await panel.getByRole('button',{name:'Download unverified draft JSON',exact:true}).click();
  const file=await waiting,buffer=await readFile(await file.path()),doc=JSON.parse(buffer);
  doc.reviewer_reference='local-only restore';
  await panel.getByLabel('Restore annotation draft JSON').setInputFiles({name:'local.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(doc))});
  await expect(panel.getByLabel('Reviewer reference (unverified)')).toHaveValue('local-only restore');
  expect(controls.records.get(id).document.reviewer_reference).toBe('synthetic persisted note');
});

test('409 retains unsaved edits and requires explicit reload before a new save',async({page})=>{
  const {panel,records,state}=await workspace(page);
  await panel.getByRole('button',{name:'Save private server draft',exact:true}).click();
  await expect(panel.getByRole('status')).toContainText('revision 1');
  const id=await panel.getByLabel('Server draft ID',{exact:true}).inputValue();
  records.get(id).revision=2;records.get(id).document.reviewer_reference='other-tab revision';
  await panel.getByLabel('Reviewer reference (unverified)').fill('keep my unsaved edits');
  await panel.getByRole('button',{name:'Save private server draft',exact:true}).click();
  await expect(panel.getByLabel('Server draft conflict',{exact:true})).toBeVisible();
  await expect(panel.getByLabel('Reviewer reference (unverified)')).toHaveValue('keep my unsaved edits');
  await expect(panel.getByRole('button',{name:'Save private server draft',exact:true})).toBeDisabled();
  expect(state.writes).toHaveLength(2);expect(state.writes[1].expected_revision).toBe(1);
  await panel.getByRole('button',{name:'Reload latest and replace local edits',exact:true}).click();
  await expect(panel.getByLabel('Reviewer reference (unverified)')).toHaveValue('other-tab revision');
  await panel.getByLabel('Reviewer reference (unverified)').fill('explicitly resolved edits');
  await panel.getByRole('button',{name:'Save private server draft',exact:true}).click();
  await expect(panel.getByRole('status')).toContainText('revision 3');
  await expect(panel.getByLabel('Saved private draft').locator('option:checked')).toContainText('revision 3');
  expect(state.writes[2].expected_revision).toBe(2);
});

test('a changed source blocks server writes and preserves local edits',async({page})=>{
  const {panel,state}=await workspace(page);
  await panel.getByLabel('Reviewer reference (unverified)').fill('source-bound unsaved edits');
  state.stale=true;
  await panel.getByRole('button',{name:'Save private server draft',exact:true}).click();
  await expect(panel.getByRole('alert')).toContainText('Source freshness');
  await expect(panel.getByLabel('Reviewer reference (unverified)')).toHaveValue('source-bound unsaved edits');
  expect(state.writes).toEqual([]);
});

test('session change during server Load cannot replace local state',async({page})=>{
  const {panel,state}=await workspace(page);
  await panel.getByRole('button',{name:'Save private server draft',exact:true}).click();
  await expect(panel.getByRole('status')).toContainText('revision 1');
  await panel.getByLabel('Reviewer reference (unverified)').fill('keep local memory');
  state.holdRead=true;
  await panel.getByRole('button',{name:'Load selected server draft and replace local edits',exact:true}).click();
  await expect.poll(()=>state.readPending).toBe(true);
  await page.evaluate(()=>localStorage.setItem('vascuai_token','different-synthetic-session'));
  state.releaseRead();
  await expect(panel.getByRole('alert')).toContainText('session changed');
  await expect(panel.getByLabel('Reviewer reference (unverified)')).toHaveValue('keep local memory');
});
