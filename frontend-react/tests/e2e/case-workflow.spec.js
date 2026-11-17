import {test,expect} from '@playwright/test';
import {readFile} from 'node:fs/promises';
import AxeBuilder from '@axe-core/playwright';
import {installApi} from './fixtures';
import {workflowFixture} from '../case-workflow-fixtures';

async function installWorkflow(page,{role='Admin',reviewed=false,outcome='accepted_for_research'}={}) {
  const requests=await installApi(page,{role});
  let state=workflowFixture({reviewed,outcome});
  await page.route('**/api/v1/cases/1/workflow',route=>route.fulfill({json:state}));
  const reviews=[];
  await page.route('**/api/v1/cases/1/reviews',async route=>{
    const body=route.request().postDataJSON();reviews.push(body);
    expect(body.reviewer_id).toBeUndefined();expect(body.reviewed_at).toBeUndefined();
    state=workflowFixture({reviewed:true,outcome:body.outcome});state.review.note=body.note;
    await route.fulfill({status:201,json:state});
  });
  return {requests,reviews,setState:value=>{state=value;}};
}

test('current saved run completes analysis; explicit authorized review completes workflow and survives reload',async({page})=>{
  const fixture=await installWorkflow(page);
  await page.goto('/cases/1');
  await expect(page.getByRole('listitem',{name:'Model analysis: complete',exact:true})).toBeVisible();
  await expect(page.getByRole('listitem',{name:'Review: not complete',exact:true})).toBeVisible();
  const submit=page.getByRole('button',{name:'Record research review',exact:true});await expect(submit).toBeDisabled();
  await page.getByLabel('Research review note (no identifying information)',{exact:true}).fill('Reviewed synthetic output for software QA.');
  await page.getByRole('checkbox',{name:/I inspected this saved segmentation/}).check();await submit.click();
  await expect(page.getByRole('status',{name:'Current research review'})).toContainText('User #1 (Admin)');
  await expect(page.getByRole('listitem',{name:'Review: complete',exact:true})).toBeVisible();
  expect(fixture.reviews).toHaveLength(1);
  await page.reload();await expect(page.getByRole('status',{name:'Current research review'})).toContainText('Accepted for research workflow');
  const download=page.waitForEvent('download');await page.getByRole('button',{name:'Workflow JSON'}).click();
  const file=await download;const body=JSON.parse(await readFile(await file.path(),'utf8'));
  expect(body.document_type).toBe('research_case_workflow');expect(body.clinical_validation).toBe(false);expect(body.workflow.review.current).toBe(true);
  const axe=await new AxeBuilder({page}).withTags(['wcag2a','wcag2aa']).analyze();expect(axe.violations).toEqual([]);
});

for(const role of ['DataScientist','Researcher'])test(`${role} can read review provenance but cannot record a decision`,async({page})=>{
  await installWorkflow(page,{role});await page.goto('/cases/1');
  await expect(page.getByText('Only an authorized Clinician or Admin can record a review.')).toBeVisible();
  await expect(page.getByRole('button',{name:'Record research review',exact:true})).toHaveCount(0);
});

test('changes requested records a decision without completing the case',async({page})=>{
  await installWorkflow(page);await page.goto('/cases/1');
  await page.getByLabel('Review outcome',{exact:true}).selectOption('changes_requested');
  await page.getByLabel('Research review note (no identifying information)',{exact:true}).fill('Reinspect the synthetic segmentation.');
  await page.getByRole('checkbox',{name:/I inspected this saved segmentation/}).check();
  await page.getByRole('button',{name:'Record research review',exact:true}).click();
  await expect(page.getByRole('status',{name:'Current research review'})).toContainText('Changes requested');
  await expect(page.locator('.page-header').getByText('Changes requested',{exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'Record research review',exact:true})).toHaveCount(0);
});

test('new run invalidates old completion while retaining historical reviewer evidence',async({page})=>{
  const fixture=await installWorkflow(page,{reviewed:true});await page.goto('/cases/1');
  await expect(page.getByRole('status',{name:'Current research review'})).toBeVisible();
  const next=workflowFixture();next.model_analysis.run.segmentation_result_id='66666666-1234-4567-890a-123456789abc';
  next.review_history=[{...workflowFixture({reviewed:true}).review,current:false}];fixture.setState(next);
  await page.getByRole('button',{name:'Refresh case workflow'}).click();
  await expect(page.getByRole('listitem',{name:'Review: not complete',exact:true})).toBeVisible();
  await expect(page.getByRole('status',{name:'Current research review'})).toHaveCount(0);
  await page.getByText('Research review history (latest 20)',{exact:true}).click();
  await expect(page.getByText(/Historical; not approval of current evidence/)).toBeVisible();
});

test('unavailable workflow stays unverified and cannot be rescued by raw legacy complete status',async({page})=>{
  await installApi(page);
  await page.route('**/api/v1/cases/3/workflow',route=>route.fulfill({status:503,json:{detail:'Workflow temporarily unavailable'}}));
  await page.goto('/cases/3');await expect(page.getByText('Workflow temporarily unavailable',{exact:true})).toBeVisible();
  await expect(page.locator('.page-header').getByText('Unverified',{exact:true})).toBeVisible();
  await expect(page.getByRole('listitem',{name:'Model analysis: not complete',exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'Record research review',exact:true})).toHaveCount(0);
});

test('conflicting review response remains an explicit error with no success state',async({page})=>{
  await installWorkflow(page);
  await page.route('**/api/v1/cases/1/reviews',route=>route.fulfill({status:409,json:{detail:'Saved output changed; refresh and inspect again.'}}));
  await page.goto('/cases/1');await page.getByRole('checkbox',{name:/I inspected this saved segmentation/}).check();
  await page.getByRole('button',{name:'Record research review',exact:true}).click();
  await expect(page.getByRole('alert')).toContainText('Saved output changed');
  await expect(page.getByRole('status',{name:'Current research review'})).toHaveCount(0);
});

test('pending review prevents duplicate submission and conflicting form changes',async({page})=>{
  const fixture=await installWorkflow(page);let release,posts=0;
  const gate=new Promise(resolve=>{release=resolve;});
  await page.route('**/api/v1/cases/1/reviews',async route=>{
    posts++;await gate;const recorded=workflowFixture({reviewed:true});fixture.setState(recorded);
    await route.fulfill({status:201,json:recorded});
  });
  await page.goto('/cases/1');await page.getByRole('checkbox',{name:/I inspected this saved segmentation/}).check();
  await page.getByRole('button',{name:'Record research review',exact:true}).click();
  await expect(page.getByRole('button',{name:'Recording review…',exact:true})).toBeDisabled();
  await expect(page.getByLabel('Review outcome',{exact:true})).toBeDisabled();
  await expect(page.getByLabel('Research review note (no identifying information)',{exact:true})).toBeDisabled();
  release();await expect(page.getByRole('status',{name:'Current research review'})).toBeVisible();expect(posts).toBe(1);
});

test('a delayed previous-case workflow cannot authorize review on a new route',async({page})=>{
  await installApi(page);let release;const gate=new Promise(resolve=>{release=resolve;});
  await page.route('**/api/v1/cases/1/workflow',async route=>{await gate;await route.fulfill({json:workflowFixture({reviewed:true})});});
  await page.goto('/cases/1');
  await page.goto('/cases/2');
  await expect(page.getByRole('heading',{name:'CASE-002',exact:true})).toBeVisible();
  release();
  await expect(page.getByRole('listitem',{name:'Model analysis: not complete',exact:true})).toBeVisible();
  await expect(page.getByRole('status',{name:'Current research review'})).toHaveCount(0);
  await expect(page.getByRole('button',{name:'Record research review',exact:true})).toHaveCount(0);
});

test('case/report filters and dashboard counts retain both new workflow states',async({page})=>{
  await installApi(page);
  const records=['awaiting_review','changes_requested'].map((status,i)=>({
    id:i+1,patient_id:1,case_code:`REVIEW-${i+1}`,study_type:'Synthetic workflow fixture',status,
    created_at:'2026-11-13T01:00:00Z',image_path:null,volume_path:null,
  }));
  await page.route('**/api/v1/cases',route=>route.fulfill({json:records}));
  await page.goto('/cases');
  await page.getByRole('button',{name:/^Awaiting review/}).click();
  await expect(page.getByRole('link',{name:'REVIEW-1',exact:true})).toBeVisible();
  await expect(page.getByRole('link',{name:'REVIEW-2',exact:true})).toHaveCount(0);
  await page.getByRole('button',{name:/^Changes requested/}).click();
  await expect(page.getByRole('link',{name:'REVIEW-2',exact:true})).toBeVisible();
  await expect(page.getByRole('link',{name:'REVIEW-1',exact:true})).toHaveCount(0);
  await page.goto('/reports');
  await page.getByLabel('Filter case summaries by status').selectOption('Awaiting review');
  await expect(page.getByRole('link',{name:'REVIEW-1',exact:true})).toBeVisible();
  await expect(page.getByRole('link',{name:'REVIEW-2',exact:true})).toHaveCount(0);
  await page.getByLabel('Filter case summaries by status').selectOption('Changes requested');
  await expect(page.getByRole('link',{name:'REVIEW-2',exact:true})).toBeVisible();
  await page.goto('/dashboard');
  for(const label of ['Awaiting review','Changes requested'])await expect(page.locator('.status-row').filter({hasText:label}).locator('strong')).toHaveText('1');
  const total=await page.locator('.status-track > span').evaluateAll(nodes=>nodes.reduce((sum,node)=>sum+parseFloat(node.style.width),0));
  expect(total).toBe(100);
});
