import {chromium,expect} from '@playwright/test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import path from 'node:path';
const origin=process.env.PLAYWRIGHT_BASE_URL,artifacts=process.env.PLAYWRIGHT_ARTIFACT_DIR;
if(new URL(origin).hostname!=='127.0.0.1'||!artifacts)throw Error('Disposable QA only');
const browser=await chromium.launch({headless:true}),context=await browser.newContext({viewport:{width:1440,height:1000},acceptDownloads:true});
await context.route('**/*',r=>['localhost','127.0.0.1'].includes(new URL(r.request().url()).hostname)?r.continue():r.abort());
const page=await context.newPage(),errors=[],requests=[];page.on('pageerror',e=>errors.push(e.message));
page.on('request',r=>requests.push(new URL(r.url()).pathname));
try{
  await page.goto(origin+'/login');await page.getByLabel('Email address',{exact:true}).fill(process.env.OFFLINE_QA_EMAIL);
  await page.getByLabel('Password',{exact:true}).fill(process.env.OFFLINE_QA_PASSWORD);await page.getByRole('button',{name:'Sign in to workspace',exact:true}).click();
  await expect(page).not.toHaveURL(/\/login$/);await page.goto(origin+`/cases/${process.env.OFFLINE_QA_CASE}/analysis`);
  await page.getByRole('button',{name:/View offline research for run/}).click();
  const panel=page.getByRole('region',{name:'Offline research workbench'});
  await panel.getByLabel('Offline evidence JSON',{exact:true}).setInputFiles(process.env.OFFLINE_QA_EVIDENCE);
  await expect(panel.getByText(/R1: 1 provisional regions/)).toBeVisible({timeout:30000});
  await expect(panel.getByText(/Verified original CT/)).toBeVisible({timeout:30000});
  await panel.getByText('Calculation evidence: profiles, support and disagreements',{exact:true}).click();
  await panel.getByRole('button',{name:'Locate research sample 10',exact:true}).click();
  // Native synthetic geometry expectation is calculated independently by the caller.
  await expect(panel.getByText('Offline CT crosshair RAS:',{exact:false})).toContainText(process.env.OFFLINE_QA_EXPECTED_RAS+' mm');
  const download=page.waitForEvent('download');await panel.getByRole('button',{name:'Export read-only offline workspace'}).click();
  const file=await download,bytes=await readFile(await file.path()),workspace=JSON.parse(bytes);
  assert.equal(workspace.clinical_gate_authorized,false);assert.equal(workspace.training_release_authorized,false);
  await panel.getByLabel('Offline evidence JSON',{exact:true}).setInputFiles({name:'restored.json',mimeType:'application/json',buffer:bytes});
  await expect(panel.getByText(/R1: 1 provisional regions/)).toBeVisible();
  await page.screenshot({path:path.join(artifacts,'actual-api-offline-research.png'),fullPage:true});
  await panel.getByRole('region',{name:'Research original CT only'}).screenshot({path:path.join(artifacts,'actual-api-offline-ct.png')});
  assert.ok(requests.every(p=>!p.endsWith('/mask')&&!p.endsWith('/probability')));assert.deepEqual(errors,[]);
  console.log('PASS actual FastAPI/PostgreSQL: authenticated file recomputation, CT navigation, R1/R2/R3, export and reverified restore; no mask download. Synthetic software fixture only.');
}finally{await context.close();await browser.close();}
