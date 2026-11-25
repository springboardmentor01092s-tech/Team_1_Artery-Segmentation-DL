import {test,expect} from '@playwright/test';
import {readFile} from 'node:fs/promises';
import {installApi} from './fixtures';

const hash='a'.repeat(64);
const sample={schema_version:'synthetic-stenosis-sample/0.2',sample_id:7,shape:[24,24,24],middle_slice_k:12,
  middle_slice:Array.from({length:24},()=>Array(24).fill(.2)),provenance:{source:'vascuai-synthetic-vessel-phantom',volume_sha256:hash},notice:'SYNTHETIC ONLY',clinical_validation:false,clinical_gate_authorized:false,training_release_authorized:false};
const analysis={schema_version:'experimental-stenosis-analysis/0.3',generated_at:'2026-11-25T00:00:00Z',status:'completed_synthetic_research_only',notice:'SYNTHETIC ONLY',
  provenance:{synthetic_sample_id:7,volume_sha256:hash,patient_case_id:null,dataset_case_id:null},
  geometry_analysis:{method:'synthetic',candidate_status:'candidate_preview',candidate_count:1,measurement_provenance:{scope:'synthetic_generated_phantom_only',input_volume_sha256:hash,method:'area-equivalent radius',axis_source:'generator-provided-synthetic-axis-not-automatically-extracted',provisional_severity_thresholds_percent:[10,30,50,70],clinical_gate_authorized:false,training_release_authorized:false},metrics:{reference_radius_synthetic_units:4,minimum_radius_synthetic_units:2,estimated_percentage_narrowing_synthetic_only:50,provisional_severity_synthetic_only:'severe',measurement_availability:'estimated_synthetic_profile_only',measurement_confidence:null,measurement_uncertainty:null,area_profile_synthetic_units2:Array(24).fill(100),position_profile_synthetic_units:Array.from({length:24},(_,i)=>i),reference_selection:'75th_percentile_of_valid_synthetic_cross_sections',trigger_ratio:.75,radial_squared_quantile:.9,peak_prominence:.05,severity_thresholds_percent_synthetic_only:[10,30,50,70]},
    candidates:[{candidate_id:'synthetic-candidate-001',status:'experimental_candidate',location:{coordinate_space:'synthetic_IJK_voxel_units',center_ijk:[12,12,12],slice_k:12,candidate_extent_synthetic_units:[10,14],bounding_box_ijk:{min:[8,8,8],max:[16,16,16]}},measurements:{minimum_radius_synthetic_units:2,reference_radius_synthetic_units:4,minimum_diameter_synthetic_units:4,reference_diameter_synthetic_units:8,estimated_percentage_narrowing_synthetic_only:50,severity_synthetic_only:'severe',severity_thresholds_percent_synthetic_only:[10,30,50,70],measurement_availability:'estimated_synthetic_only',measurement_confidence:null,measurement_uncertainty:null,quality:'synthetic_geometry_only_unvalidated'}}]},
  model:{model_id:'synthetic-3d-cnn',model_version:'0.1.0',checkpoint_sha256:hash,predicted_synthetic_class:'moderate',class_probabilities_uncalibrated:[.1,.2,.4,.2,.1],score_semantics:'uncalibrated_softmax_probability_not_clinical_confidence',clinical_performance_claim:false},
  explainability:{method:'3d-cnn-grad-cam',target_class:'moderate',shape:[24,24,24],heatmap_values:Array(24**3).fill(.25),scope:'synthetic_generated_phantom_only'},clinical_validation:false,clinical_gate_authorized:false,training_release_authorized:false};

test('research user generates synthetic sample, runs analysis, reviews candidate and exports JSON',async({page})=>{
  await installApi(page,{role:'DataScientist'});
  await page.route('**/api/v1/experimental-stenosis/status',route=>route.fulfill({json:{available:true,reason:null,scope:'synthetic_generated_phantoms_only',clinical_gate_authorized:false,training_release_authorized:false}}));
  await page.route('**/api/v1/experimental-stenosis/samples',async route=>{const body=route.request().postDataJSON();expect(body).toEqual({sample_id:7,synthetic_class_id:2,seed:1729});return route.fulfill({json:sample});});
  await page.route('**/api/v1/experimental-stenosis/analyze',async route=>{const body=route.request().postDataJSON();expect(body).toEqual({sample_id:7,synthetic_class_id:2,seed:1729,provisional_severity_thresholds_percent:[10,30,50,70]});return route.fulfill({json:analysis});});
  await page.goto('/research/experimental-stenosis');
  await expect(page.getByRole('heading',{name:'Experimental Stenosis Analysis'})).toBeVisible();
  await expect(page.getByRole('note')).toContainText('Synthetic research only');
  await page.getByLabel('Sample ID').fill('7');await page.getByLabel('Synthetic class').selectOption('2');await page.getByLabel('Deterministic seed').fill('1729');
  await page.getByRole('button',{name:'Generate phantom'}).click();
  await expect(page.getByRole('heading',{name:'Synthetic sample 7'})).toBeVisible();
  await expect(page.getByRole('img',{name:'Synthetic vessel phantom central slice'})).toBeVisible();
  await page.getByRole('button',{name:'Run experimental analysis'}).click();
  await expect(page.getByRole('heading',{name:'Experimental result'})).toBeVisible();
  await expect(page.getByRole('rowheader',{name:'moderate',exact:true})).toBeVisible();await expect(page.getByRole('rowheader',{name:'severe',exact:true})).toBeVisible();
  await expect(page.getByRole('img',{name:'Synthetic-only model Grad-CAM central slice'})).toBeVisible();
  await expect(page.getByRole('table',{name:'Provisional synthetic candidates only'})).toContainText('50.0%');
  const downloadPromise=page.waitForEvent('download');await page.getByRole('button',{name:'Export research JSON'}).click();
  const download=await downloadPromise;expect(download.suggestedFilename()).toBe('vascuai-synthetic-stenosis-7.json');
  const exported=JSON.parse(await readFile(await download.path(),'utf8'));
  expect(exported.provenance).not.toHaveProperty('synthetic_class_label');
  expect(JSON.stringify(exported)).not.toContain('synthetic_geometry_ground_truth');
});

test('unavailable checkpoint leaves model action disabled but sample generation remains explicit',async({page})=>{
  await installApi(page,{role:'Researcher'});
  await page.route('**/api/v1/experimental-stenosis/status',route=>route.fulfill({json:{available:false,reason:'checkpoint not configured',scope:'synthetic_generated_phantoms_only',clinical_gate_authorized:false,training_release_authorized:false}}));
  await page.route('**/api/v1/experimental-stenosis/samples',route=>route.fulfill({json:sample}));
  await page.goto('/research/experimental-stenosis');
  await expect(page.getByRole('status')).toContainText('checkpoint not configured');
  await expect(page.getByRole('button',{name:'Run experimental analysis'})).toBeDisabled();
  await page.getByRole('button',{name:'Generate phantom'}).click();
  await expect(page.getByRole('heading',{name:'Synthetic sample 7'})).toBeVisible();
});

test('changing synthetic parameters invalidates an in-flight analysis result',async({page})=>{
  await installApi(page,{role:'DataScientist'});
  await page.route('**/api/v1/experimental-stenosis/status',route=>route.fulfill({json:{available:true,reason:null,scope:'synthetic_generated_phantoms_only',clinical_gate_authorized:false,training_release_authorized:false}}));
  await page.route('**/api/v1/experimental-stenosis/samples',route=>route.fulfill({json:sample}));
  await page.route('**/api/v1/experimental-stenosis/analyze',async route=>{await new Promise(resolve=>setTimeout(resolve,400));return route.fulfill({json:analysis});});
  await page.goto('/research/experimental-stenosis');
  await page.getByLabel('Sample ID').fill('7');await page.getByLabel('Synthetic class').selectOption('2');await page.getByLabel('Deterministic seed').fill('1729');
  await page.getByRole('button',{name:'Generate phantom'}).click();await expect(page.getByRole('heading',{name:'Synthetic sample 7'})).toBeVisible();
  await page.getByRole('button',{name:'Run experimental analysis'}).click();
  await page.getByLabel('Deterministic seed').fill('1730');
  await expect(page.getByRole('heading',{name:'Synthetic sample 7'})).toHaveCount(0);
  await page.waitForTimeout(500);await expect(page.getByRole('heading',{name:'Experimental result'})).toHaveCount(0);
});

test('clinician role is denied before experimental API calls',async({page})=>{
  await installApi(page,{role:'Clinician'});
  await page.route('**/api/v1/experimental-stenosis/**',()=>{throw new Error('Clinical role must not request synthetic research endpoints');});
  await page.goto('/research/experimental-stenosis');
  await expect(page.getByRole('heading',{name:'This area needs different access.'})).toBeVisible();
});

test('real-volume mode uploads a separate CT/mask pair and displays measurement abstention',async({page})=>{
  const real={schema_version:'real-volume-research/0.1',status:'profile_only',notice:'REAL-VOLUME RESEARCH QC ONLY',
    provenance:{ct_sha256:hash,mask_file_sha256:'b'.repeat(64),persisted:false,synthetic_model_used:false},
    geometry:{shape_ijk:[24,24,24],orientation:['R','A','S'],ct_spatial_units:'mm',mask_spatial_units:'unknown',voxel_spacing_native:[.6,.8,1.1],voxel_spacing_mm:[.6,.8,1.1],affine_ras_mm:[],geometry_source:'CT NIfTI'},
    segmentation:{semantics:'supplied_coronary_artery_segmentation_unverified_lumen',foreground_voxels:224,component_count_26:1,component_voxel_counts_descending:[224],component_list_truncated:false},
    centerline:{status:'abstained',reasons:['source_loop_cavity_or_non_tree_topology'],branches:[],diagnostics:{}},
    candidates:[],candidate_status:'unavailable_mask_semantics_unverified',
    measurements:{reference_lumen_area_mm2:null,minimum_lumen_area_mm2:null,reference_lumen_diameter_mm:null,minimum_lumen_diameter_mm:null,estimated_percentage_narrowing:null,provisional_severity:null,availability:'unavailable_lumen_semantics_unverified'},
    clinical_validation:false,clinical_gate_authorized:false,training_release_authorized:false};
  await installApi(page,{role:'DataScientist'});
  await page.route('**/api/v1/experimental-stenosis/status',route=>route.fulfill({json:{available:false,reason:'synthetic checkpoint unavailable',scope:'synthetic_generated_phantoms_only',clinical_gate_authorized:false,training_release_authorized:false}}));
  await page.route('**/api/v1/experimental-stenosis/real-volume/analyze',async route=>{
    const request=route.request();
    expect(request.headers()['content-type']).toContain('multipart/form-data');
    const body=request.postDataBuffer().toString('latin1');
    expect(body).toContain('name="ct_volume"'); expect(body).toContain('name="vessel_mask"');
    return route.fulfill({json:real});
  });
  await page.goto('/research/experimental-stenosis');
  await page.getByLabel('CT volume (.nii or .nii.gz)').setInputFiles({name:'original.nii',mimeType:'application/octet-stream',buffer:Buffer.from('ct-fixture')});
  await page.getByLabel('Matching binary vessel mask (.nii or .nii.gz)').setInputFiles({name:'mask.nii.gz',mimeType:'application/octet-stream',buffer:Buffer.from('mask-fixture')});
  await page.getByRole('button',{name:'Validate and analyze pair'}).click();
  await expect(page.getByRole('heading',{name:'Ephemeral research result: profile_only'})).toBeVisible();
  await expect(page.getByText('Candidate localization')).toBeVisible();
  await expect(page.getByText('Unavailable — mask lumen semantics are not verified')).toBeVisible();
  await expect(page.getByText('Percentage narrowing / provisional severity')).toBeVisible();
  await expect(page.getByText('false / false')).toBeVisible();
});

test('real-volume result and selected files are cleared when authorization changes in flight',async({page})=>{
  await installApi(page,{role:'Researcher'});
  await page.route('**/api/v1/experimental-stenosis/status',route=>route.fulfill({json:{available:false,reason:'optional synthetic model unavailable',scope:'synthetic_generated_phantoms_only',clinical_gate_authorized:false,training_release_authorized:false}}));
  await page.route('**/api/v1/experimental-stenosis/real-volume/analyze',async route=>{
    await new Promise(resolve=>setTimeout(resolve,350));
    return route.fulfill({status:500,json:{detail:'test response must be ignored after authorization change'}});
  });
  await page.goto('/research/experimental-stenosis');
  await page.getByLabel('CT volume (.nii or .nii.gz)').setInputFiles({name:'private-ct.nii',mimeType:'application/octet-stream',buffer:Buffer.from('ct-fixture')});
  await page.getByLabel('Matching binary vessel mask (.nii or .nii.gz)').setInputFiles({name:'private-mask.nii',mimeType:'application/octet-stream',buffer:Buffer.from('mask-fixture')});
  await page.getByRole('button',{name:'Validate and analyze pair'}).click();
  await page.evaluate(()=>window.dispatchEvent(new Event('vascuai:unauthorized')));
  await page.waitForTimeout(450);
  await expect(page.getByRole('heading',{name:/Ephemeral research result/})).toHaveCount(0);
  const ctInput=page.getByLabel('CT volume (.nii or .nii.gz)');
  const maskInput=page.getByLabel('Matching binary vessel mask (.nii or .nii.gz)');
  if(await ctInput.count())expect(await ctInput.evaluate(input=>input.files.length)).toBe(0);
  if(await maskInput.count())expect(await maskInput.evaluate(input=>input.files.length)).toBe(0);
});
