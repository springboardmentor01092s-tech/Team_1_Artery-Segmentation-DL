// UI transport tests: actual serialized Python synthetic output, intercepted API.
import {test,expect} from '@playwright/test';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {installApi} from './fixtures';
import {loadExperimentalFixture} from '../experimental-candidates-fixtures';
import AxeBuilder from '@axe-core/playwright';
const evidence=JSON.parse(readFileSync(new URL('../fixtures/offline-research-synthetic.json',import.meta.url),'utf8'));
const text=JSON.stringify(evidence);
async function open(page,{delay=false}={}){
  await installApi(page,{role:'Researcher'});const f=await loadExperimentalFixture(),requests=[],errors=[];let release;
  let maskHash=evidence.record.source_files.mask_file_sha256;
  page.on('pageerror',e=>errors.push(e.message));
  page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
  await page.route('**/api/v1/cases/1/segmentations**',async route=>{
    const req=route.request(),path=new URL(req.url()).pathname;requests.push([req.method(),path]);
    if(path.endsWith('/research-evidence/identity'))return route.fulfill({json:{schema_version:'offline-research-source/0.1',case_id:1,segmentation_result_id:f.segmentation.id,
      mask_file_sha256:maskHash,segmentation:f.segmentation,clinical_gate_authorized:false,training_release_authorized:false}});
    if(path.endsWith('/research-evidence/verify')){
      if(delay)await new Promise(resolve=>{release=resolve;});
      const e=JSON.parse(req.postData());
      return route.fulfill({json:{schema_version:'verified-offline-research/0.1',procedure_version:'0.1',case_id:1,segmentation_result_id:f.segmentation.id,
        evidence_sha256:createHash('sha256').update(req.postData()).digest('hex'),verified_at:'2026-11-24T10:00:00Z',profile:e.record.profile,
        source_files:e.record.source_files,implementation_sha256:e.record.implementation_sha256,segmentation:f.segmentation,
        verification_scope:'recomputed_against_current_stored_files_not_clinical_attestation',clinical_gate_authorized:false,training_release_authorized:false}});
    }
    if(path.endsWith('/segmentations'))return route.fulfill({json:[f.segmentation]});
    if(path.endsWith('/source'))return route.fulfill({contentType:'application/gzip',body:f.ctGzip});
    throw Error(`Offline display must never request mask/prediction: ${path}`);
  });
  await page.goto('/cases/1/analysis');await page.getByRole('button',{name:/View offline research for run/}).click();
  const panel=page.getByRole('region',{name:'Offline research workbench'});
  const load=content=>panel.getByLabel('Offline evidence JSON',{exact:true}).setInputFiles({name:'synthetic.json',mimeType:'application/json',buffer:Buffer.from(content)});
  return {panel,load,requests,errors,release:()=>release?.(),invalidateMask:()=>{maskHash='f'.repeat(64);}};
}

test('read-only profile, CT navigation, R1/R2/R3, export and fresh restore never download mask',async({page})=>{
  const {panel,load,requests,errors}=await open(page);await load(text);
  await expect(panel.getByText(/R1: 1 provisional regions/)).toBeVisible();
  await expect(panel.getByText(/Verified original CT/)).toBeVisible({timeout:30000});
  await panel.getByText('Calculation evidence: profiles, support and disagreements',{exact:true}).click();
  await panel.getByRole('button',{name:'Locate research sample 10',exact:true}).click();
  await expect(panel.getByText(/Offline CT crosshair RAS: 0.00, 0.00, 7.00 mm/)).toBeVisible();
  const download=page.waitForEvent('download');await panel.getByRole('button',{name:'Export read-only offline workspace'}).click();
  const stream=await (await download).createReadStream(),chunks=[];for await(const b of stream)chunks.push(b);
  const exported=Buffer.concat(chunks).toString(),workspace=JSON.parse(exported);
  expect(workspace.clinical_gate_authorized).toBe(false);expect(workspace.training_release_authorized).toBe(false);
  workspace.assessment_sha256='f'.repeat(64);await load(JSON.stringify(workspace));await expect(panel.getByRole('alert')).toContainText('hash/procedure/source mismatch');
  await load(exported);await expect(panel.getByText(/R1: 1 provisional regions/)).toBeVisible();
  expect(requests.filter(([method])=>method==='POST').length).toBeGreaterThanOrEqual(5);
  expect(requests.every(([,path])=>!path.endsWith('/mask')&&!path.endsWith('/probability'))).toBe(true);
  const a11y=await new AxeBuilder({page}).include('[aria-label="Offline research workbench"]').analyze();expect(a11y.violations).toEqual([]);
  await panel.screenshot({path:test.info().outputPath('offline-research-synthetic.png')});
  await page.emulateMedia({media:'print'});await expect(panel).toBeHidden();expect(errors).toEqual([]);
});

test('oversized import rejected before request and delayed response cannot survive session change',async({page})=>{
  const {panel,load,requests,release}=await open(page,{delay:true});
  await load('x'.repeat(2*1024*1024+1));await expect(panel.getByRole('alert')).toContainText('at most 2 MiB');expect(requests.filter(([m])=>m==='POST')).toHaveLength(0);
  await load(text);await expect.poll(()=>requests.filter(([m])=>m==='POST').length).toBe(1);
  await page.evaluate(()=>localStorage.setItem('vascuai_token','changed-synthetic-session'));release();
  await expect(panel.getByRole('alert')).toContainText('Session');await expect(panel.getByText(/R1: 1 provisional regions/)).toHaveCount(0);
});

test('source freshness on refocus clears an idle profile and CT after stored mask changes',async({page})=>{
  const {panel,load,invalidateMask,requests}=await open(page);await load(text);
  await expect(panel.getByText(/R1: 1 provisional regions/)).toBeVisible();invalidateMask();
  await page.evaluate(()=>window.dispatchEvent(new Event('focus')));
  await expect(panel.getByRole('alert')).toContainText('Research source identity or access could not be verified');
  await expect(panel.getByText(/R1: 1 provisional regions/)).toHaveCount(0);
  await expect(panel.getByRole('region',{name:'Research original CT only'})).toHaveCount(0);
  expect(requests.filter(([,p])=>p.endsWith('/mask')||p.endsWith('/probability'))).toHaveLength(0);
});
