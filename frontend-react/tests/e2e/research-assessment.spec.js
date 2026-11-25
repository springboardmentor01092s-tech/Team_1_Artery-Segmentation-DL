// Synthetic CT + actual extractor output only. No patient data or database writes.
import { test, expect } from '@playwright/test';
import { installApi } from './fixtures';
import { loadExperimentalFixture } from '../experimental-candidates-fixtures';
import AxeBuilder from '@axe-core/playwright';

async function open(page) {
  const writes=[],errors=[];
  page.on('request',request=>{if(request.method()!=='GET')writes.push(request.url());});
  page.on('pageerror',error=>errors.push(error.message));
  page.on('console',message=>{if(message.type()==='error')errors.push(message.text());});
  await installApi(page,{role:'Researcher'});
  const f=await loadExperimentalFixture();
  await page.route('**/api/v1/cases/1/segmentations**',route=>{
    const path=new URL(route.request().url()).pathname;
    return path.endsWith('/segmentations')?route.fulfill({json:[f.segmentation]}):route.fulfill({contentType:'application/gzip',body:path.endsWith('/source')?f.ctGzip:f.maskGzip});
  });
  await page.goto('/cases/1/analysis');
  await page.getByRole('button',{name:`View CT + Segmentation for run ${f.segmentation.id}`}).click();
  await expect(page.getByText(/Voxel spacing \(original axes\):/)).toBeVisible({timeout:30000});
  await page.getByText('Experimental local candidate preview',{exact:true}).click();
  await page.getByLabel('Local experimental candidate JSON',{exact:true}).setInputFiles({name:'synthetic-profile.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(f.preview))});
  const workspace=page.getByRole('region',{name:'Provisional research assessments'});
  await expect(workspace).toBeVisible();
  return {workspace,writes,errors};
}
test('simulated assessments, source-bound download/restore and caliper arithmetic stay separate from human reviews',async({page})=>{
  const {workspace,writes,errors}=await open(page);
  await workspace.getByRole('button',{name:'Run provisional research assessments'}).click();
  await expect(workspace.getByText('R3: provisional comparison',{exact:true})).toBeVisible();
  await expect(workspace.getByText(/Confidence: unavailable \(not calibrated\)/)).toBeVisible();
  await expect(workspace.getByText(/Manual caliper status: unassessable/)).toBeVisible();
  const download=page.waitForEvent('download');
  await workspace.getByRole('button',{name:'Download standalone research JSON'}).click();
  const file=await download,stream=await file.createReadStream(),chunks=[];
  for await(const chunk of stream)chunks.push(chunk);
  const data=JSON.parse(Buffer.concat(chunks).toString());
  expect(data.document.clinical_gate_authorized).toBe(false);expect(data.document.training_release_authorized).toBe(false);
  expect(data.document.records[2].record.parent_sha256).toEqual(data.document.records.slice(0,2).map(row=>row.sha256));
  const restore=data=>workspace.getByLabel('Restore standalone research JSON',{exact:true}).setInputFiles({name:'research.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(data))});
  const bad=structuredClone(data);bad.document.records[0].record.confidence=.99;
  await restore(bad);await expect(workspace.getByRole('alert')).toContainText('content/hash/source mismatch');
  await expect(workspace.getByText('R3: provisional comparison',{exact:true})).toHaveCount(0);
  await restore(data);await expect(workspace.getByText('R3: provisional comparison',{exact:true})).toBeVisible();
  await workspace.getByText('Optional unverified caliper arithmetic',{exact:true}).click();
  for(const [key,value]of Object.entries({minimum_start_ijk:'15,16,34',minimum_end_ijk:'16,16,34',reference_start_ijk:'14,16,20',reference_end_ijk:'16,16,20'}))await workspace.getByLabel(`Research ${key}`,{exact:true}).fill(value);
  await workspace.getByLabel('Research method evidence',{exact:true}).fill('Synthetic in-plane arithmetic only. No anatomical reference verification.');
  await workspace.getByRole('button',{name:'Run provisional research assessments'}).click();
  await expect(workspace.getByText(/Unverified arithmetic only: 50.000%/)).toBeVisible();
  await workspace.getByRole('button',{name:'Locate R1-main-1',exact:true}).click();
  await expect(page.getByText('Crosshair RAS: 0.00, 0.00, 27.00 mm',{exact:false})).toBeVisible();
  await expect(workspace.getByRole('button',{name:'Locate R1-main-1',exact:true})).toBeEnabled();
  await workspace.getByText('Calculation evidence: profiles, support and disagreements',{exact:true}).click();
  await expect(workspace.getByRole('img',{name:'Research area profiles and unresolved disagreements'})).toBeVisible();
  await workspace.getByRole('button',{name:'Locate research sample 10',exact:true}).click();
  await expect(page.getByText('Crosshair RAS: 0.00, 0.00, 7.00 mm',{exact:false})).toBeVisible();
  await expect(workspace.getByText(/Selected sample 10, s=10.000 mm; native IJK 16.000, 16.000, 14.000/)).toBeVisible();
  const a11y=await new AxeBuilder({page}).include('[aria-label="Provisional research assessments"]').analyze();
  expect(a11y.violations).toEqual([]);
  await workspace.screenshot({path:test.info().outputPath('synthetic-provisional-research.png')});
  await page.emulateMedia({media:'print'});await expect(workspace).toBeHidden();
  expect(writes).toEqual([]);expect(errors).toEqual([]);
});
test('a delayed local profile cannot load into a changed session',async({page})=>{
  const {workspace,writes,errors}=await open(page);
  const f=await loadExperimentalFixture();
  await page.evaluate(()=>{
    const original=File.prototype.text;let release;
    const pause=new Promise(resolve=>{release=resolve;});window.releaseResearchFile=release;
    File.prototype.text=async function(){await pause;return original.call(this);};
  });
  await page.getByLabel('Local experimental candidate JSON',{exact:true}).setInputFiles({name:'delayed-profile.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(f.preview))});
  await expect(workspace).toHaveCount(0);
  await page.evaluate(()=>{localStorage.setItem('vascuai_token','different-synthetic-session');window.releaseResearchFile();});
  await expect(page.getByRole('alert')).toContainText('Session changed; no experimental preview accepted');
  await expect(workspace).toHaveCount(0);expect(writes).toEqual([]);expect(errors).toEqual([]);
});
test('a delayed research operation cannot complete after token changes, even without a storage event',async({page})=>{
  const {workspace,writes,errors}=await open(page);
  await page.evaluate(()=>{
    const original=crypto.subtle.digest.bind(crypto.subtle);let release;
    const pause=new Promise(resolve=>{release=resolve;});
    window.releaseResearchHash=release;
    crypto.subtle.digest=async(...args)=>{await pause;return original(...args);};
  });
  await workspace.getByRole('button',{name:'Run provisional research assessments'}).click();
  await expect(workspace.getByRole('status')).toBeVisible();
  await page.evaluate(()=>{localStorage.setItem('vascuai_token','different-synthetic-session');window.releaseResearchHash();});
  await expect(workspace.getByRole('alert')).toContainText('Session changed');
  await expect(workspace.getByText('R3: provisional comparison',{exact:true})).toHaveCount(0);
  await expect(workspace.getByRole('button',{name:'Download standalone research JSON'})).toBeDisabled();
  expect(writes).toEqual([]);expect(errors).toEqual([]);
});
