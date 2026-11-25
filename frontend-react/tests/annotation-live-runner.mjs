// Opt-in disposable PostgreSQL/FastAPI UI verification. Credentials are supplied
// only by the parent synthetic test process, never written to a fixture or log.
import {chromium} from '@playwright/test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import path from 'node:path';

const origin=process.env.PLAYWRIGHT_BASE_URL,caseId=Number(process.env.ANNOTATION_QA_CASE),runId=process.env.ANNOTATION_QA_RUN;
const artifacts=process.env.PLAYWRIGHT_ARTIFACT_DIR;
if(new URL(origin).hostname!=='127.0.0.1'||!Number.isSafeInteger(caseId)||!runId||!artifacts)throw new Error('Disposable live test configuration required');
const browser=await chromium.launch({headless:true,args:['--use-angle=swiftshader','--enable-unsafe-swiftshader']});
const context=await browser.newContext({viewport:{width:1440,height:1000}});
await context.route('**/*',route=>['127.0.0.1','localhost'].includes(new URL(route.request().url()).hostname)?route.continue():route.abort());
const errors=[];context.on('page',page=>page.on('pageerror',error=>errors.push(error.message)));
const page=await context.newPage();
const expect=(await import('@playwright/test')).expect;
async function login(target) {
  await target.goto(`${origin}/login`);
  await target.getByLabel('Email address',{exact:true}).fill(process.env.ANNOTATION_QA_EMAIL);
  await target.getByLabel('Password',{exact:true}).fill(process.env.ANNOTATION_QA_PASSWORD);
  await target.getByRole('button',{name:'Sign in to workspace',exact:true}).click();
  await expect(target).not.toHaveURL(/\/login$/);
}
async function open(target) {
  await target.goto(`${origin}/cases/${caseId}/analysis`);
  await target.getByRole('button',{name:`View CT + Segmentation for run ${runId}`}).click();
  await target.getByText('Prepare a local lesion review draft',{exact:true}).click();
  return target.getByLabel('Local lesion annotation draft',{exact:true});
}
async function load(panel,id) {
  await panel.getByRole('button',{name:'Refresh my saved drafts',exact:true}).click();
  await panel.getByLabel('Saved private draft').selectOption(id);
  await panel.getByRole('button',{name:'Load selected server draft and replace local edits',exact:true}).click();
  await expect(panel.getByRole('status')).toContainText('Loaded your private server draft');
}
try {
  await login(page);const first=await open(page);
  await first.getByLabel('Reviewer reference (unverified)').fill('synthetic live draft');
  const created=page.waitForResponse(r=>r.url().endsWith('/annotation-drafts')&&r.request().method()==='POST');
  await first.getByRole('button',{name:'Save private server draft',exact:true}).click();
  const response=await created;assert.equal(response.status(),201);const saved=await response.json(),id=saved.id;
  assert.equal(saved.owner_id,Number(process.env.ANNOTATION_QA_OWNER));
  assert.equal(saved.clinical_gate_authorized,false);assert.equal(saved.training_release_authorized,false);
  await expect(first.getByRole('status')).toContainText('revision 1');
  const secondPage=await context.newPage(),second=await open(secondPage);await load(second,id);
  await first.getByLabel('Reviewer reference (unverified)').fill('first tab revision two');
  await first.getByRole('button',{name:'Save private server draft',exact:true}).click();
  await expect(first.getByRole('status')).toContainText('revision 2');
  await second.getByLabel('Reviewer reference (unverified)').fill('second tab unsaved edits');
  const conflicted=secondPage.waitForResponse(r=>r.url().endsWith(id)&&r.request().method()==='PUT');
  await second.getByRole('button',{name:'Save private server draft',exact:true}).click();
  assert.equal((await conflicted).status(),409);
  await expect(second.getByLabel('Server draft conflict',{exact:true})).toBeVisible();
  await expect(second.getByLabel('Reviewer reference (unverified)')).toHaveValue('second tab unsaved edits');
  await expect(second.getByRole('button',{name:'Save private server draft',exact:true})).toBeDisabled();
  const downloaded=secondPage.waitForEvent('download');
  await second.getByRole('button',{name:'Download unverified draft JSON',exact:true}).click();
  const download=await downloaded,local=await readFile(await download.path());
  await second.getByRole('button',{name:'Reload latest and replace local edits',exact:true}).click();
  await expect(second.getByLabel('Reviewer reference (unverified)')).toHaveValue('first tab revision two');
  await second.getByLabel('Reviewer reference (unverified)').fill('explicitly resolved live revision');
  await second.getByRole('button',{name:'Save private server draft',exact:true}).click();
  await expect(second.getByRole('status')).toContainText('revision 3');
  await expect(second.getByLabel('Saved private draft').locator('option:checked')).toContainText('revision 3');
  await secondPage.screenshot({path:path.join(artifacts,'actual-api-server-draft.png'),fullPage:true});
  await secondPage.getByRole('button',{name:'Sign out',exact:true}).click();
  await expect(secondPage).toHaveURL(/\/login$/);
  await login(secondPage);const restored=await open(secondPage);await load(restored,id);
  await expect(restored.getByLabel('Reviewer reference (unverified)')).toHaveValue('explicitly resolved live revision');
  await restored.getByLabel('Restore annotation draft JSON').setInputFiles({name:'synthetic-local-draft.json',mimeType:'application/json',buffer:local});
  await expect(restored.getByLabel('Reviewer reference (unverified)')).toHaveValue('second tab unsaved edits');
  const token=await secondPage.evaluate(()=>localStorage.getItem('vascuai_token'));
  const headers={Authorization:`Bearer ${token}`};
  const persisted=await secondPage.request.get(`${origin}/api/v1/cases/${caseId}/annotation-drafts/${id}`,{headers});
  assert.equal(persisted.status(),200);assert.equal((await persisted.json()).revision,3);
  assert.equal((await persisted.json()).document.reviewer_reference,'explicitly resolved live revision');
  const replacement=await readFile(process.env.ANNOTATION_QA_REPLACEMENT);
  const upload=await secondPage.request.post(`${origin}/api/v1/cases/${caseId}/volume`,{headers,
    multipart:{file:{name:'different-synthetic-ct.nii.gz',mimeType:'application/gzip',buffer:replacement}}});
  assert.equal(upload.status(),200);
  const writes=[];secondPage.on('request',r=>{if(['POST','PUT'].includes(r.method())&&r.url().includes('/annotation-drafts'))writes.push(r.url());});
  await restored.getByRole('button',{name:'Save private server draft',exact:true}).click();
  await expect(restored.getByRole('alert')).toContainText('Source freshness');
  assert.deepEqual(writes,[]);
  const stale=await secondPage.request.get(`${origin}/api/v1/cases/${caseId}/annotation-drafts/${id}`,{headers}),staleBody=await stale.json();
  assert.equal(stale.status(),200);assert.equal(staleBody.source_current,false);assert.equal(staleBody.revision,3);
  assert.equal(staleBody.clinical_gate_authorized,false);assert.equal(staleBody.training_release_authorized,false);
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({actual_HTTP:true,mocked_API_responses:false,synthetic_CT:true,
    create:201,conflicting_update:409,resolved_revision:3,logout_login_persisted:true,
    local_JSON_did_not_save:true,source_change_blocked:true,clinical_gate_authorized:false,training_release_authorized:false}));
} finally {await browser.close();}
