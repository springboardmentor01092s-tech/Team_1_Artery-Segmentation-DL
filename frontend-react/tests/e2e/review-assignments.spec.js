// Explicit synthetic UI contracts. Actual server authorization is tested on PG.
import {test,expect} from '@playwright/test';
import {installApi} from './fixtures';
const id='11111111-1111-4111-8111-111111111111';
const flags={clinical_gate_authorized:false,training_release_authorized:false,reader_independence_verified:false,qualification_verified:false};
const source={case_id:1,source_sha256:'a'.repeat(64),shape:[5,7,9],affine:[[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]],units:'mm'};
const item={id,reviewer_id:1,slot:'R1',case_id:1,protocol_version:'synthetic-unapproved',source,
  geometry_identity:{version:'ct-geometry/1.0',sha256:'b'.repeat(64)},review_mode:'original_ct_only',...flags};
async function setup(page,role='Clinician'){
  await installApi(page,{role});const state={revision:0,notes:'',stale:false,writes:[],hold:false};
  await page.route('**/api/v1/review-assignments**',async route=>{
    const req=route.request(),path=new URL(req.url()).pathname;
    if(path.endsWith('/review-assignments'))return route.fulfill({json:{items:[item],limit:50,offset:0,next_offset:null,offset_limit_reached:false,...flags}});
    if(path.endsWith('/draft')){
      if(req.method()==='PUT'){
        const data=req.postDataJSON();state.writes.push(data);
        if(data.expected_revision!==state.revision)return route.fulfill({status:409,json:{detail:'Revision conflict'}});
        state.notes=data.notes;state.revision++;
      }
      if(state.hold){state.pending=true;await new Promise(resolve=>{state.release=resolve;});}
      return route.fulfill({status:req.method()==='PUT'&&state.revision===1?201:200,json:{schema_version:'ct-review-note/0.1',assignment_id:id,
        owner_id:1,case_id:1,protocol_version:item.protocol_version,source,revision:state.revision,notes:state.notes,exists:state.revision>0,status:'unverified_draft',...flags}});
    }
    return route.fulfill({json:{...item,source_current:!state.stale,source_unavailable_reason:state.stale?'Bound CT changed.':null}});
  });
  await page.goto('/review-assignments');await page.getByLabel('Assignment',{exact:true}).selectOption(id);
  return state;
}
test('private notes have explicit revision conflict resolution and logout/login persistence',async({page})=>{
  const state=await setup(page);await page.getByRole('button',{name:'Load selected assignment',exact:true}).click();
  const input=page.getByLabel('Private unverified preparation notes');await expect(input).toBeVisible();
  await input.fill('synthetic private notes');await page.getByRole('button',{name:'Save private review draft',exact:true}).click();
  await expect(page.getByText('Server revision: 1.',{exact:false})).toBeVisible();
  state.revision=2;state.notes='other tab';await input.fill('retain my notes');
  await page.getByRole('button',{name:'Save private review draft',exact:true}).click();
  await expect(input).toHaveValue('retain my notes');await expect(page.getByRole('button',{name:'Save private review draft',exact:true})).toBeDisabled();
  await page.getByRole('button',{name:'Reload latest and replace my notes',exact:true}).click();await expect(input).toHaveValue('other tab');
  await page.getByRole('button',{name:'Sign out',exact:true}).click();
  await page.getByLabel('Email address',{exact:true}).fill('alex@example.test');await page.getByLabel('Password',{exact:true}).fill('synthetic-test-only');
  await page.getByRole('button',{name:'Sign in to workspace',exact:true}).click();await expect(page).not.toHaveURL(/\/login$/);
  await page.goto('/review-assignments');await page.getByLabel('Assignment',{exact:true}).selectOption(id);
  await page.getByRole('button',{name:'Load selected assignment',exact:true}).click();await expect(input).toHaveValue('other tab');
  expect(state.writes).toHaveLength(2);expect(state.writes.every(r=>r.clinical_gate_authorized===false&&r.training_release_authorized===false)).toBe(true);
});
test('changed CT disables writes and download without substituting any prediction',async({page})=>{
  const state=await setup(page);state.stale=true;await page.getByRole('button',{name:'Load selected assignment',exact:true}).click();
  await expect(page.getByRole('button',{name:'Save private review draft',exact:true})).toBeDisabled();
  await expect(page.getByRole('button',{name:'Download verified original CT',exact:true})).toBeDisabled();
  await expect(page.getByText('Bound CT changed.',{exact:false})).toBeVisible();expect(state.writes).toHaveLength(0);
});
test('old-session pending note load cannot restore content after logout',async({page})=>{
  const state=await setup(page);state.hold=true;state.revision=1;state.notes='old session private text';
  await page.getByRole('button',{name:'Load selected assignment',exact:true}).click();await expect.poll(()=>state.pending).toBe(true);
  await page.getByRole('button',{name:'Sign out',exact:true}).click();await expect(page).toHaveURL(/\/login$/);
  state.release();await expect(page.getByText('old session private text')).toHaveCount(0);
});
test('coordinator assigns distinct accounts to a verified original CT without receiving findings',async({page})=>{
  await installApi(page,{role:'Admin'});let submitted;
  await page.route('**/api/v1/admin/users**',r=>r.fulfill({json:[{id:2,full_name:'Synthetic R1',role:'Clinician',is_active:true},{id:3,full_name:'Synthetic R2',role:'Clinician',is_active:true}]}));
  await page.route('**/api/v1/review-assignments**',r=>r.fulfill({json:{items:[],limit:50,offset:0,next_offset:null,offset_limit_reached:false,...flags}}));
  await page.route('**/api/v1/review-studies**',r=>{
    if(r.request().method()==='GET')return r.fulfill({json:{case_id:1,source,geometry_identity:item.geometry_identity,...flags}});
    submitted=r.request().postDataJSON();return r.fulfill({status:201,json:{id,case_id:1,source,protocol_version:submitted.protocol_version,
      assignments:[{id,slot:'R1',reviewer_id:2},{id:'22222222-2222-4222-8222-222222222222',slot:'R2',reviewer_id:3}],...flags}});
  });
  await page.goto('/review-assignments');await page.getByLabel('Review case',{exact:true}).selectOption('1');
  await page.getByRole('button',{name:'Inspect original CT identity',exact:true}).click();await expect(page.getByText('Verified original CT SHA-256:',{exact:false})).toBeVisible();
  await page.getByLabel('R1 reviewer',{exact:true}).selectOption('2');await page.getByLabel('R2 reviewer',{exact:true}).selectOption('2');
  await page.getByLabel('Protocol version',{exact:true}).fill('synthetic-unapproved');await page.getByRole('checkbox').check();
  await expect(page.getByRole('button',{name:'Create R1/R2 assignments',exact:true})).toBeDisabled();
  await page.getByLabel('R2 reviewer',{exact:true}).selectOption('3');await page.getByRole('button',{name:'Create R1/R2 assignments',exact:true}).click();
  await expect(page.getByText('Case 1 assigned. Only assignment metadata is shown.')).toBeVisible();
  expect(submitted.expected_ct_sha256).toBe(source.source_sha256);expect(submitted.r1_user_id).toBe(2);expect(submitted.r2_user_id).toBe(3);
});
