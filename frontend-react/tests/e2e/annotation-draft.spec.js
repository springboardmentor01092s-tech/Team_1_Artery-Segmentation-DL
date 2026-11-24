// Synthetic software fixtures; no expert annotations or application DB writes.
import { test, expect } from '@playwright/test';
import { readFile } from 'node:fs/promises';
import AxeBuilder from '@axe-core/playwright';
import { installApi } from './fixtures';
import { loadExperimentalFixture } from '../experimental-candidates-fixtures';

async function open(page,role='Admin',layout='flipped') {
  await installApi(page,{role});
  const fixture=await loadExperimentalFixture(layout),{segmentation:parent,ctGzip:ct,maskGzip:mask}=fixture;
  let stale=false;
  await page.route('**/api/v1/cases/1/segmentations**',route=>{
    const path=new URL(route.request().url()).pathname;
    return path.endsWith('/segmentations') ? route.fulfill({json:[{...parent,stale}]}) :
      route.fulfill({contentType:'application/gzip',body:path.endsWith('/source')?ct:mask});
  });
  await page.goto('/cases/1/analysis');
  await page.getByRole('button',{name:`View CT + Segmentation for run ${parent.id}`}).click();
  await expect(page.getByText(/Voxel spacing \(original axes\):/)).toBeVisible({timeout:30000});
  return {...fixture,stale:()=>{stale=true;}};
}

for(const [role,layout] of [['Admin','flipped'],['Clinician','permuted']])test(`source-bound local annotation capture, download and restore (${role}, ${layout})`,async({page},testInfo)=>{
  const errors=[],writes=[];
  page.on('pageerror',e=>errors.push(e.message));
  page.on('request',r=>{if(r.method()!=='GET')writes.push(r.url());});
  const fixture=await open(page,role,layout);
  // Locate a fixed synthetic backend-fixture point, then test actual native CT
  // point capture. This is a coordinate test, not an expert lesion annotation.
  await page.getByText('Experimental local candidate preview',{exact:true}).click();
  await page.getByLabel('Local experimental candidate JSON',{exact:true}).setInputFiles({name:'synthetic-preview.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(fixture.preview))});
  await page.getByRole('button',{name:'Locate experimental candidate-001 (main)',exact:true}).click();
  await page.getByText('Prepare a local lesion review draft',{exact:true}).click();
  const panel=page.getByLabel('Local lesion annotation draft',{exact:true});
  await expect(panel).toContainText('not a blinded independent reading');
  await panel.getByRole('button',{name:'Add proposed lesion worksheet',exact:true}).click();
  await panel.getByRole('button',{name:'Capture Lesion center',exact:true}).click();
  await expect(panel.getByText('Native IJK: 16, 16, 34',{exact:true})).toBeVisible();
  expect((await new AxeBuilder({page}).include('[aria-label="Local lesion annotation draft"]').analyze()).violations).toEqual([]);
  await panel.getByLabel('Minimum lumen diameter (mm)',{exact:true}).fill('0');
  const download=page.waitForEvent('download');
  await panel.getByRole('button',{name:'Download unverified draft JSON',exact:true}).click();
  const file=await download,value=JSON.parse(await readFile(await file.path(),'utf8'));
  expect(value.source.source_sha256).toBe(fixture.segmentation.metadata.source_sha256);
  expect(value.proposed_lesions[0].center_ijk).toEqual([16,16,34]);
  expect(value.proposed_lesions[0].minimum_lumen_diameter_mm).toBe(0);
  expect(value.proposed_lesions[0].percentage_narrowing).toBeNull();
  expect(value.proposed_lesions[0].severity_category).toBeNull();
  expect(value.clinical_validation).toBe(false);expect(value.training_eligible).toBe(false);
  expect(value.clinical_gate_authorized).toBe(false);expect(value.training_release_authorized).toBe(false);
  await panel.getByLabel('Restore annotation draft JSON').setInputFiles({name:'draft.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(value))});
  await expect(panel.getByRole('status')).toContainText('Source-matched local draft restored');
  await panel.getByRole('button',{name:'Remove selected worksheet',exact:true}).click();
  await expect(panel).toContainText('No lesion worksheet added. This does not mean that stenosis is absent.');
  await panel.getByLabel('Restore annotation draft JSON').setInputFiles({name:'draft.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(value))});
  await expect(panel.getByText('Native IJK: 16, 16, 34',{exact:true})).toBeVisible();
  const bad=structuredClone(value);bad.source.source_sha256='f'.repeat(64);
  await panel.getByLabel('Restore annotation draft JSON').setInputFiles({name:'wrong.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(bad))});
  await expect(panel.getByRole('alert')).toContainText('mismatched annotation draft');
  expect(writes).toEqual([]);expect(errors).toEqual([]);
  await page.screenshot({path:testInfo.outputPath(`annotation-draft-${layout}.png`),fullPage:true});
  await page.setViewportSize({width:390,height:844});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=document.documentElement.clientWidth+1)).toBe(true);
  fixture.stale();
  await panel.getByRole('button',{name:'Download unverified draft JSON',exact:true}).click();
  await expect(panel.getByRole('alert')).toContainText('Source freshness could not be verified');
});

for(const role of ['Researcher','DataScientist'])test(`${role} read role cannot author a local lesion worksheet`,async({page})=>{
  await open(page,role);
  await expect(page.getByText('Local lesion worksheet entry is available to Clinician and Admin roles.',{exact:false})).toBeVisible();
  await expect(page.getByRole('button',{name:'Add proposed lesion worksheet',exact:true})).toHaveCount(0);
});

test('session change during file decoding cannot restore an old-session draft',async({page})=>{
  await open(page);
  await page.getByText('Prepare a local lesion review draft',{exact:true}).click();
  const panel=page.getByLabel('Local lesion annotation draft',{exact:true});
  const reviewer=panel.getByLabel('Reviewer reference (unverified)');
  await reviewer.fill('old-session-software-probe');
  const waiting=page.waitForEvent('download');
  await panel.getByRole('button',{name:'Download unverified draft JSON',exact:true}).click();
  const download=await waiting,buffer=await readFile(await download.path());
  await reviewer.fill('current-memory-draft');
  await page.evaluate(()=>{
    const original=File.prototype.text;
    File.prototype.text=function(){
      window.draftDecodeStarted=true;
      return new Promise(resolve=>{window.releaseDraftDecode=()=>original.call(this).then(resolve);});
    };
  });
  await panel.getByLabel('Restore annotation draft JSON').setInputFiles({name:'old-session.json',mimeType:'application/json',buffer});
  await expect.poll(()=>page.evaluate(()=>Boolean(window.draftDecodeStarted))).toBe(true);
  await page.evaluate(()=>{
    // Same-tab replacement without a storage event reproduces the original race.
    localStorage.setItem('vascuai_token','replacement-software-test-session');
    window.releaseDraftDecode();
  });
  await expect(panel.getByRole('alert')).toContainText('session changed');
  await expect(reviewer).toHaveValue('current-memory-draft');
  await expect(panel.getByText('Source-matched local draft restored.',{exact:false})).toHaveCount(0);
});

async function savedDraft(page) {
  const fixture=await open(page);
  await page.getByText('Prepare a local lesion review draft',{exact:true}).click();
  const panel=page.getByLabel('Local lesion annotation draft',{exact:true});
  const waiting=page.waitForEvent('download');
  await panel.getByRole('button',{name:'Download unverified draft JSON',exact:true}).click();
  const download=await waiting,buffer=await readFile(await download.path());
  return {fixture,panel,buffer};
}

for(const operation of ['download','restore'])test(`${operation} rejects a session change during source verification`,async({page})=>{
  const {fixture,panel,buffer}=await savedDraft(page),downloads=[];
  page.on('download',value=>downloads.push(value));
  let held;
  await page.route('**/api/v1/cases/1/segmentations',route=>{held=route;});
  if(operation==='restore')await panel.getByLabel('Restore annotation draft JSON').setInputFiles({name:'draft.json',mimeType:'application/json',buffer});
  else await panel.getByRole('button',{name:'Download unverified draft JSON',exact:true}).click();
  await expect.poll(()=>Boolean(held)).toBe(true);
  await page.evaluate(()=>localStorage.setItem('vascuai_token','changed-during-source-check'));
  await held.fulfill({json:[{...fixture.segmentation,stale:false}]});
  await expect(panel.getByRole('alert')).toContainText('session changed');
  await expect(panel.getByRole('status')).toHaveCount(0);
  expect(downloads).toEqual([]);
});

for(const change of ['role','identity'])test(`same-token server ${change} change prevents draft download`,async({page})=>{
  const {panel}=await savedDraft(page),downloads=[];
  page.on('download',value=>downloads.push(value));
  await page.evaluate(()=>{
    window.annotationBlobs=0;
    window.Blob=new Proxy(Blob,{construct(target,args,newTarget){
      if(args[1]?.type==='application/json;charset=utf-8')window.annotationBlobs++;
      return Reflect.construct(target,args,newTarget);
    }});
  });
  await page.route('**/api/v1/auth/me',route=>route.fulfill({json:{id:change==='identity'?2:1,
    role:change==='role'?'Researcher':'Admin',is_active:true,full_name:'Synthetic reader'}}));
  await panel.getByRole('button',{name:'Download unverified draft JSON',exact:true}).click();
  await expect(panel.getByRole('alert')).toContainText('Writer authorization changed');
  expect(downloads).toEqual([]);
  expect(await page.evaluate(()=>window.annotationBlobs)).toBe(0);
});

for(const kind of ['singular','invalid','mismatched'])test(`public JSON restore refuses ${kind} geometry without changing the draft`,async({page})=>{
  const {panel,buffer}=await savedDraft(page),value=JSON.parse(buffer);
  if(kind==='singular')value.source.affine[0]=[0,0,0,0];
  if(kind==='invalid')value.source.affine[3][0]=1;
  if(kind==='mismatched')value.source.affine[0][3]++;
  value.reviewer_reference='must-not-be-restored';
  await panel.getByLabel('Reviewer reference (unverified)').fill('keep-current-draft');
  await panel.getByLabel('Restore annotation draft JSON').setInputFiles({name:'invalid-geometry.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(value))});
  await expect(panel.getByRole('alert')).toContainText('Invalid or mismatched annotation draft');
  await expect(panel.getByLabel('Reviewer reference (unverified)')).toHaveValue('keep-current-draft');
});

test('all seven landmark buttons preserve native CT coordinates',async({page})=>{
  const {panel}=await savedDraft(page);
  await panel.getByRole('button',{name:'Add proposed lesion worksheet',exact:true}).click();
  for(const name of ['Lesion center','Proximal boundary','Distal boundary','Minimum caliper start','Minimum caliper end','Reference caliper start','Reference caliper end']) {
    await panel.getByRole('button',{name:`Capture ${name}`,exact:true}).click();
  }
  const waiting=page.waitForEvent('download');
  await panel.getByRole('button',{name:'Download unverified draft JSON',exact:true}).click();
  const download=await waiting,value=JSON.parse(await readFile(await download.path(),'utf8'));
  for(const key of ['center_ijk','proximal_boundary_ijk','distal_boundary_ijk','minimum_caliper_start_ijk','minimum_caliper_end_ijk','reference_caliper_start_ijk','reference_caliper_end_ijk']) {
    expect(value.proposed_lesions[0][key]).toEqual([16,16,48]);
  }
});

test('unmount during file decoding cannot apply the old restore to a reopened viewer',async({page})=>{
  const {fixture,panel,buffer}=await savedDraft(page);
  const value=JSON.parse(buffer);value.reviewer_reference='old-unmounted-viewer';
  await page.evaluate(()=>{
    const original=File.prototype.text;
    File.prototype.text=function(){window.pendingDecode=true;return new Promise(resolve=>{
      window.releasePendingDecode=()=>original.call(this).then(resolve);
    });};
  });
  await panel.getByLabel('Restore annotation draft JSON').setInputFiles({name:'draft.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(value))});
  await expect.poll(()=>page.evaluate(()=>Boolean(window.pendingDecode))).toBe(true);
  await page.getByRole('button',{name:'Close viewer',exact:true}).click();
  await page.evaluate(()=>window.releasePendingDecode());
  await page.getByRole('button',{name:`View CT + Segmentation for run ${fixture.segmentation.id}`}).click();
  await page.getByText('Prepare a local lesion review draft',{exact:true}).click();
  await expect(page.getByLabel('Reviewer reference (unverified)')).toHaveValue('');
});
