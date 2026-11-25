# Milestone completion report

## M3 synthetic geometry measurement validation — 25 November 2026

This is a separate, bounded synthetic benchmark increment; it does not upgrade
clinical capability or change the prior M1/M2/M4 evidence. Source remains at
`e37b7c87eebe5099686687eacd6a6db897d2e6c7`; no staging access or deployment was
performed. Benchmark artifact: `F:\vascuai-artifacts\runs\m3-synthetic-geometry-measurement-20261125T093700Z\measurement-benchmark.json` (repeat run `T094000Z` produced an identical SHA-256).

- [x] Added an independently evaluated phantom benchmark for reference radius,
  minimum radius, percentage narrowing and candidate localization.
- [x] Ground truth is held by the benchmark and stripped before estimator calls.
- [x] The 180-case matrix spans five synthetic classes, six IJK axes/orientations,
  three noise levels and two replicates; it contains 216 generated lesions.
- [x] UI and research JSON now expose provisional geometry measurements, method
  provenance and configurable research-only category thresholds.
- [ ] Synthetic geometry measurements and categories are not clinically validated;
  expert lesion labels, physical calibration and independent clinical review remain
  unavailable. Confidence and uncertainty are explicitly null.
- [ ] Frozen CNN results are a separate experimental artifact and are not evidence
  for geometric measurement accuracy or clinical stenosis performance.

The frozen synthetic CNN remains unchanged (SHA-256
`a264d54a1fb4c370673ecaa7f8d3733982c0132b6e88e83dab1993cabb497937`). Its separate
500-phantom held-out synthetic evaluation recorded macro-F1 0.2887; it is weak and
not patient performance. The synthetic geometry baseline macro-F1 0.9594 uses
generator-provided geometry and is an oracle-like comparator, not a fair inference
baseline. Neither result is clinical evidence.

Benchmark results: 207/216 lesions matched (recall 0.9583), precision 1.0,
multiple-lesion recall 0.9375, and no false candidate among 36 normal phantoms.
Across 180 profiles, reference-radius MAE/RMSE/bias were 0.3098/0.3265/-0.3098
synthetic voxels; minimum-radius 0.2278/0.2853/-0.2245 synthetic voxels; and
percentage-narrowing 2.2917/3.5759/+0.9953 percentage points. Matched lesion
localization MAE/RMSE/signed bias were 0.3574/0.4331/+0.0139 axial voxels. Absolute
error p50/p90/max were 0.2996/0.4089/0.8253 for reference radius, 0.1798/0.4888/
0.7448 for minimum radius, 1.4844/5.0143/13.0818 percentage points for profile
narrowing, and 0.3551/0.6391/1.2844 axial voxels for matched localization. These
measure this controlled generator only. Provisional severity used configured synthetic thresholds
10/30/50/70%; matched-candidate accuracy was 0.9855. The maximum percentage error
was 13.0818 points, so aggregate scores do not remove meaningful failures.

Both authorization flags remain false. No patient data, Validation/Testing split,
database, or deployed service was used by this increment. See `TEST_EVIDENCE.md`
and `docs/milestone3-research-completion.md` for commands and test outcomes.

Final integration audit: Milestone 3 remains **partial** against the official
requirements. The isolated synthetic workflow is suitable for a carefully labelled
research demonstration, not a clinical/real-scan stenosis demonstration. Earlier
M1/M2/M4 results were exercised by broad regressions but were not recertified here.

---

## Final engineering sprint ? verified scope

Updated 24 November 2026. Evidence: `final-engineering-20261124T093721Z`.
Branch `codex/milestone3-review`; HEAD remains `e37b7c87eebe5099686687eacd6a6db897d2e6c7`.
At report time, changes were local and unstaged. The later preflight staged all 164 pending paths locally; no commit, push, merge, staging migration or deployment has occurred.

- [x] M1 foundations and current design/architecture documentation preserved.
- [x] M2 fresh verification: exact 50-case cohort/model, all 100 predictions and
  original-reference counts/hashes/native numeric grids; 53 comparison artifacts
  reproduce byte-for-byte. No inference/threshold or training-data change.
- [x] M3 restricted automatic branch-to-profile CLI, integrity/provenance checks,
  14-case analytic acceptance and a real synthetic NIfTI-to-profile demonstration.
- [x] M3 idle source invalidation and actual-API browser verification up to a
  4,276,737-voxel synthetic CT source without browser mask download.
- [x] M4 embedded third-reader CT, source/protocol documentation counts, SQL credential
  eligibility/pagination and full private-workspace clearing on session changes.
- [x] M4 owner-only append-only unverified amendment records with source, parent,
  revision and hash-chain validation; 37 focused PostgreSQL migration/reviewer tests pass.
- [x] Broad available PostgreSQL regression rerun: 881 passed, 13 skipped, 3 warnings;
  frontend 650 passed; lint/build and diff checks pass.
- [ ] General automatic extraction: only 4/14 configurations admitted, 10 abstain;
  existing source-support/topology/even-width/resource refusals are unchanged.
- [ ] M3 expert lesion supervision, classifier/severity/calibrated confidence/stenosis XAI unavailable.
- [ ] M4 R3 cannot adjudicate amendment records yet; assignment withdrawal/reassignment,
  full packet receipts, protocol/qualification sign-off remain incomplete.
- [ ] Current coordinated real backup/restore, approved images/migrations/release remain pending.

The automatic bridge retains every node/edge of admitted trees, verifies native
coordinates/source hashes, and emits no sampling plan for refused topology. Explicit
Training/synthetic requests only, native coded mm geometry, unchanged 4M-voxel limit,
no pruning/relabel/resampling/invented branches. Four admitted synthetic configurations
(narrow, Y, multi-branch, oblique Y) meet stated spatial/topology checks; anisotropic
Y and other failures remain abstentions. This is not general anatomical validation.

The third-reader pane uses a separate authenticated adjudication loader, one original
CT and no overlays or independent-reader worksheet. Frozen parent hashes, source,
geometry and credentials are rechecked. Coverage counts are documentation fields,
not anatomical coverage or correctness; packet/sign-off/evidence receipts remain
explicitly unverified. SQL filters now match all existing credential prerequisites
before pagination; hidden ineligible records do not affect page metadata.

Fresh final evidence: frontend 650 passed; PostgreSQL 881 passed/13 skipped;
scientific 211 passed; full browser 216 passed/3 skipped; offline API 25 passed;
actual-API reviewer + small/native research 3 passed; SQLite auth/review/cleanup
76 passed/3 PG-only skips; synthetic schema restore 1 passed. Build/lint/diff pass.
Counts overlap. The broad backend suite excludes nine SciPy-dependent research
modules; additional missing-Torch, opt-in and Windows symlink tests are skipped.
Warnings and skip reasons are documented in TEST_EVIDENCE.md.

Read-only staging: schema 0010, older b47d74a images, health/readiness 200; protected
case/evaluation GETs 401 and new reviewer route 404. Retained backup integrity/ACL/
archive/pg_restore-list pass, but schema 0009 backup freshness fails. No actual staging
backup/restore/migration/restart/deployment was executed. Both authorization flags false.

---

## Prior entries (preserved)

## Latest increment ? offline evidence browser integration and final documentation

Evidence: external run `m3-browser-centerlines-20261124T082756Z`, 24 November 2026.
Branch/HEAD remain `codex/milestone3-review` / `e37b7c87eebe5099686687eacd6a6db897d2e6c7`.
All changes are local, unstaged and undeployed.

- [x] M1 foundations and architecture/wireframes preserved; final individual HTML/PDF added.
- [x] M2 completed 50-case comparison, checkpoints and evaluation artifacts preserved.
- [x] M3 versioned offline evidence import, authenticated stored-file recomputation,
  read-only R1/R2/R3 evidence, CT-only navigation and reverified export/restore implemented.
- [x] M4 owner/private/CT-only review implementation and all migrations preserved.
- [ ] M3 reliable automatic branches remain unresolved; supplied branches are required.
- [ ] Clinical labels/model/severity/stenosis attribution remain unavailable.
- [ ] M4 real qualification/independence, complete external packet operations,
  current-schema coordinated backup/restore and approved release remain outstanding.

The API resolves current stored CT/prediction paths, recomputes the complete bounded
profile, compares all fields/code/environment identities, then rechecks actor/session,
source freshness, metadata and mask SHA-256. The browser accepts only a fresh transport
receipt, never a supplied verified flag. Evidence display does not load the full mask;
optional original CT retains existing rendering budgets and oblique refusal.
Research wrappers are rejected by both ordinary JSON export paths. No clinical or
training record is created. Both authorizations remain false.

Eight new small synthetic probes: one accepted Y tree, seven abstentions (support,
loop, disconnected, even-width loss and boundary reasons). All eight safety tests
pass, but this is not general extraction success. The frozen 20-case matrix and
instrumentation were not rerun, no guard relaxed and no old research source modified.

Fresh results: frontend 636 passed; available PostgreSQL 868 passed/12 skipped;
scientific research 178 passed; offline API 22 passed; actual-API offline browser
1 passed; complete browser 213 passed/3 skipped; build/lint/diff exit 0.
Counts overlap and are not summed. Existing chunk/Fast Refresh/deprecation warnings
remain. See TEST_EVIDENCE.md and docs/offline-research-evidence.md.

Final documentation: standalone website-themed HTML plus searchable A4 PDF under
docs/final-individual-project-documentation.*, with 11 diagrams, actual model metrics,
genuine synthetic QA screenshots, issue register, contributions and evidence limits.
No new clinical gate, dependency/lockfile, schema migration, model inference/training,
staging backup/restore, commit, push, merge or deployment was performed.

---

## Historical entries (preserved)

Updated 24 November 2026 11:14 IST. Local increment `m3-completion-20261124T051538Z`; branch/HEAD unchanged. No commit, push, merge, staging migration or deployment.

## Current increment: native-volume research and calculation evidence

- Implemented a bounded offline full-native-mask path: streamed categorical identity,
  exact six-connected frontier counting, mapped plane gathers and the shared original
  supplied-branch sampler. No crop, resampling, component discard or threshold change.
- Verified a 4,276,737-voxel anisotropic synthetic NIfTI run above the old in-memory
  limit; repeated full profile hashes match. Source files/geometry remain unchanged.
- Added source-linked R1/R2 area/reference/trigger profiles, support windows, unavailable
  gaps, raw triggers versus accepted regions, disagreement bands and sample navigation.
- Strengthened caliper geometry, malformed inputs, export isolation, deterministic
  replay, sampling/threshold/reference/contiguous-support boundary coverage and axe checks.
- Restarted only the pinned disposable QA database. PostgreSQL: 868 passed/10 skipped;
  actual-API reviewer rehearsal: 1 passed. Frontend: 622 passed. Research backend:
  119 passed. Full browser: 211 passed/3 skipped. Build/lint/diff checks passed.

See `docs/milestone3-research-completion.md` for the requirement/code/test matrix,
exact commands, corrected failures, files and limits. M1/M2 results and M4 source
are preserved. Qualified lesion supervision, a trained stenosis model, clinical
severity and stenosis attribution remain unavailable. Both authorizations stay false.

The offline tool requires supplied ordered branches, explicit coded millimetres,
uint8 masks and strict resource budgets. It does not solve reliable automatic branch
extraction. Browser large-mask/oblique limits remain; full native-volume output can
be inspected in a desktop viewer. Current new execution evidence is synthetic,
not a real-patient or actual stenosis-model demonstration. Release remains blocked.


---

## Prior sprint evidence (historical, preserved)

Updated 24 November 2026 10:15 IST. Evidence: external run `ai-assisted-m3-20261124T042751Z`. Branch and HEAD unchanged. All new work remains local, unstaged and undeployed.

## Provisional research implementation completed in this stage

Implemented a separate local workbench within CT + predicted segmentation:
source/mask/geometry verification; two distinct numerical assessments (R1 median
interpolation, R2 conservative directional mean); R3 section-level disagreement
comparison; source-bound provisional candidate coordinates/bounds; area-equivalent
research measurements; optional native-IJK caliper arithmetic; explicit unavailable
confidence/artery/severity/attribution; hash-linked frozen local records and verified
standalone JSON restore/export. Normal report exports refuse these records.

These are deterministic simulated assessment procedures, not three trained AI
models, LLM agents or qualified independent reviewers. Shared input errors remain.
The AI input can be an actual saved segmentation prediction; current new execution
evidence uses synthetic backend-generated mask/profile fixtures, not new patient
inference. There is no new full-volume automatic branch/candidate service.

The asymmetric fixture produced one R1 proposal, zero R2 proposals and five
unresolved section disagreements. R3 retained both originals without converting
agreement/disagreement into ground truth. Repeated research packet hashes match.
Research diameter reduction is explicitly unverified; clinical/training flags remain
false. No clinical gate, severity/classifier or training-label generation was enabled.

Fresh checks: frontend 607 passed; browser 25 passed; backend profile/schema 39
passed; isolated quantitative safety 29 passed; build/lint/diff checks exit 0.
PostgreSQL re-verification stopped before tests because the pinned disposable QA
container is exited. It was not started/replaced. Older PG evidence is historical.

## Milestone progress

- [x] M1 foundations and current architecture/wireframe deliverables retained.
  Historical Week 1 evidence and mentor sign-off remain external.
- [x] M2 50-case comparison completed previously; evidence rechecked, not rerun.
  SegResNet macro Dice 0.755683, SmallUNet3D 0.105181; protocol/centerline limits remain.
- [ ] M3 partially implemented: source-bound research proposals, visualization,
  simulated comparison and unverified arithmetic now work. Qualified lesion labels,
  a trained stenosis detector, validated severity and genuine stenosis XAI remain absent.
- [ ] M4 reviewer core preserved; clinical review credentials, current-schema backup,
  approved release and deployment remain outstanding.

See `docs/provisional-research-assessments.md`. In-memory freezing and downloadable
hash-linked packets are not authenticated immutable AI submission storage. No
server-side simulated-agent history or AI reviewer service has been implemented.
Existing blinded human review isolation and immutable records are not reused for AI.


---

## Previous completed sprint evidence (retained; not a fresh rerun)

Updated 24 November 2026 09:41 IST. Branch `codex/milestone3-review`; base HEAD `e37b7c87eebe5099686687eacd6a6db897d2e6c7`. New code is uncommitted and undeployed. External evidence run: `completion-sprint-20261123T171203Z`.

## Segmentation comparison completed

| Model | Measured | Macro Dice | Macro IoU | Macro precision | Macro recall |
|---|---|---|---|---|---|
| SmallUNet3D | 50/50 | 0.105181 | 0.055990 | 0.060377 | 0.459152 |
| MONAI SegResNet | 50/50 | 0.755683 | 0.609950 | 0.783651 | 0.735917 |


Same 50 Split-4 Val cases (851-900), unchanged original reference masks. All 100
prediction files passed SHA-256, numerical-grid, binary-value, confusion-count and
metric recomputation. Each macro denominator is 50; pooled micro results are separate.
Per-case CSV, full JSON and Markdown: external `comparison-50/`. A repeat saved-mask
verification produced identical hashes for all 53 report/snapshot artifacts.
Eight verifier self-tests passed. No inference was rerun for the repeat.

SmallUNet3D: native grid, threshold 0.70; original training run/verified optimizer
count unresolved (step 700 is a checkpoint label). SegResNet: 1 mm recipe, linear
probability interpolation to native grid then threshold 0.50; saved 200-Training/
50-Val run preserved. Training/grids/thresholds differ: not an architecture-only
controlled comparison. Val selected the checkpoint; no independent Testing or
clinical performance claim. Reference spatial units remain unresolved: numerical
voxel correspondence does not prove anatomical registration.

The stale 39/50 status had progressed to 43 usable saved results plus a wall-limit
interruption at 894. Only 894-900 ran in the new bounded continuation. All 43 results
were reused, including historical 851/852. Numerical worker/configuration and
per-case/memory/output caps stayed unchanged. Original interruption evidence for
877 and 894 is retained. No thresholds, checkpoints or evaluation records changed.

## Reviewer software implemented

- 4B core: source-bound CT-only manual worksheet, seven native-IJK landmarks,
  manual evidence/unavailable states, private revisions/history, conflict handling
  and separate local JSON. Resource-blocked volumes retain verified download and
  explicit external-viewer IJK entry; display caps and integrity refusals remain.
- 4C: immutable independent submissions, source/version hashes, idempotency and
  concurrent-save/submission protection.
- 4D core: separately credential-gated third account after both frozen reviews,
  API isolation, correspondence/discrepancies/unresolved decisions, bounded recent
  history, old-version access and immutable hash-linked finalization.

All outputs remain unverified. Both clinical and training-release flags stay false,
including after adjudication. No real credential or expert annotation was seeded.
Full expert-packet integration remains partial: verified inventory/case mapping,
evidence-file receipts, diagnostic coverage and protocol/qualification signoff.
Amendments/reassignment and embedded third-reader viewing are absent; verified CT
download is available. See `docs/independent-lesion-review.md`.

## Other completion and remaining work

M1 architecture and current wireframes were added/corrected; no historical Week 1
artifact/date is invented. M3 research/quantitative safeguards were preserved and
ordinary JSON additionally rejects abstained automatic research wrappers. Automatic
centerline source-support/skeleton limits are not claimed resolved. Qualified lesion
supervision, a stenosis classifier, validated localization/severity/percentage and
genuine stenosis XAI remain blocked; software tests cannot supply those labels.

Fresh results: frontend 572 passed; full available PG 868 passed/10 skipped; browser
208 passed/3 intentional skips; focused reviewer/migration/restore 27 passed; actual-
API manual-entry/three-reader rehearsal passed; CPU Torch 74 passed/2 platform skips;
vessel/candidate 84 passed. Counts overlap. See `TEST_EVIDENCE.md`.

Staging health/readiness is 200 but schema remains 0010 and new review routes are
absent. Pending release migrations: 0011-0015. Retained backup integrity/ACL checks
pass but its schema is 0009, stale for current 0010. Fresh coordinated backup,
compatible rollback, image verification and deployment approval remain required.
No commit, push, merge, real migration, service restart, deployment or real backup/
restore was executed. Only disposable QA databases were written.

## 2026-11-25 follow-up: structured report PDF

Added a server-rendered, structured stenosis research-report PDF download using the existing authorized report snapshot. The document uses persisted report fields only and preserves unavailable values and the non-clinical limitations. Synthetic completed (zero and two candidate records) and failed/status-only reports were generated and visually inspected; one-page and two-page layouts were readable, page headers/footers were present, and extracted text contained no replacement characters or webpage chrome.

Fresh checks: backend stenosis-reporting PostgreSQL suite 26 passed; frontend unit suite 651 passed; reporting browser suite 16 passed (API mocked); frontend production build passed with a large-chunk advisory; lint exited 0 with the existing AuthContext fast-refresh warning; `git diff --check` passed. The PDF change is local and undeployed. The full application spacing/responsive audit remains incomplete; no stenosis classifier, expert lesion labels, clinical measurement gate, validated severity or clinical validation was added.

## 2026-11-25 Milestone 3 dataset check

A fresh primary-source review found no currently usable lesion-level supervision for VascuAI's 3D CTA workflow. ImageCAS/ImageCAS-X has artery masks but no verified lesion labels; ASOCA is 3D CTA with patient-level normal/diseased status but is closed access; Zenodo 4638863 is restricted pending ethics evidence; ARCADE has 2D X-ray lesion masks, but its modality is incompatible and the Zenodo license field is blank. Details and source links are in `docs/milestone3-research-completion.md`. No restricted dataset was accessed, and at that point no synthetic model had been trained. The following increment adds one synthetic-only experiment; it does not add clinical outputs or enable gates.

## 2026-11-25 synthetic-only M3 implementation increment

Added an optional, isolated CPU-capable 3D CNN experiment under `backend/app/services/synthetic_stenosis_ml.py` with a CLI in `backend/scripts/train_synthetic_stenosis.py`. It procedurally generates noisy oblique vessel phantoms and controlled synthetic classes, creates disjoint sample-ID train/validation/test splits, trains a 3D CNN, selects a checkpoint by validation loss, evaluates once on the held-out synthetic test split, and provides provenance-restricted synthetic inference and genuine 3D Grad-CAM. Patient volumes are refused unless they exactly reproduce from the generator seed and class. No API, database, report, or patient-case path consumes these outputs.

Actual training completed in an isolated Python 3.14 / PyTorch 2.15.0+cpu environment: 500 generated samples (300/100/100), 50 epochs, seed 1729. Held-out synthetic metrics: accuracy 0.31, macro precision 0.3152, macro recall 0.31, macro F1 0.3076 (n=100; chance baseline is 0.20). This weak result demonstrates the training/evaluation pipeline, not a useful classifier. Checkpoint: `F:\vascuai-artifacts\runs\milestone3-synthetic-cnn-20261125T1245-v5+0530\synthetic-stenosis-cnn3d.pt`; SHA-256 `a264d54a1fb4c370673ecaa7f8d3733982c0132b6e88e83dab1993cabb497937`. The synthetic dataset identity is recorded in the adjacent summary.

A fixed synthetic moderate-class smoke phantom was also predicted as normal; this checkpoint is not suitable even as a robust synthetic classifier.

Three optional-model tests passed, including checkpoint reload, provenance refusal, held-out metrics, Grad-CAM output shape and false authorization flags. Combined offline research/model suite: **214 passed**. This model is not exposed by FastAPI or the case viewer/dashboard and is not trained on real CTA. The existing source-bound geometric profile/viewer remains separate. Severity bins exist only as synthetic generator labels; no clinical severity, percentage, diagnosis, or model XAI for patient images is available. Both authorization flags remain false. No Docker build, database change, deployment, commit or push occurred. M3 remains incomplete.

## 2026-11-25 synthetic-only dashboard integration

Added a separate authenticated `/research/experimental-stenosis` workbench backed by `GET /api/v1/experimental-stenosis/status`, `POST /samples`, and `POST /analyze`. Requests accept only bounded synthetic sample/class/seed fields; the server regenerates the phantom, verifies an externally configured checkpoint by absolute path and SHA-256, checks its synthetic-only metadata, and returns generated-source provenance, geometry candidate/profile output, uncalibrated 3D CNN scores and 3D Grad-CAM. Clinician access is denied; Admin, Data Scientist and Researcher roles are admitted. Results are not persisted and never enter case APIs, clinical reporting, analytics or training-release paths. Both authorization flags are false.

The page renders generated phantom slices, candidate markers, area profile, provisional synthetic-only category/voxel-based reduction, uncalibrated model scores, Grad-CAM and a downloadable research JSON. It explicitly labels the work as synthetic research only. The UI was corrected to consume the backend's actual `estimated_percentage_narrowing_synthetic_only` field and severity thresholds under `geometry_analysis.metrics`.

Fresh verification: frontend unit suite **658 passed**; focused Experimental Stenosis Playwright flow **4 passed** (mock API browser flows, including unavailable checkpoint, clinician denial, and stale in-flight result invalidation after changing parameters); `npm run lint` exit 0 with two warnings in the new page plus the existing AuthContext warning; production build passed with existing large-chunk warning; Python `compileall` passed; `git diff --check` and cached diff check passed. The normal backend pytest setup could not collect because the available worktree interpreter lacks `reportlab`. Focused `--noconftest` API/model tests passed **6 tests** using ephemeral test settings and the pre-existing isolated CPU PyTorch package directory; this exercised TestClient routes, temporary checkpoint verification/inference, and Grad-CAM without application DB access. The existing external v5 checkpoint was separately verified by exact SHA and completed a generated-phantom inference/Grad-CAM smoke test (3 candidates; predicted synthetic class `normal`; both authorization flags false). No dependencies were installed. No migration, Docker or deployment action occurred. M3 remains incomplete: the checkpoint is weak on synthetic holdout data, no qualified real lesion labels exist, no real-patient analysis is available, and this dashboard result is non-persistent synthetic research output only.

## 25 Nov 2026 — synthetic-only Milestone 3 verification

This entry records the current worktree verification; it does not replace earlier milestone evidence. Branch and HEAD remain `codex/milestone3-review` / `e37b7c87eebe5099686687eacd6a6db897d2e6c7`. The 164 staged paths were preserved. New changes are unstaged/untracked; no commit, push, deployment, staging access, patient inference or clinical-gate change occurred.

- **M1:** Previously recorded architecture/setup and wireframe artifacts are preserved. This run did not re-audit external requirement sign-off.
- **M2:** Previously recorded 50-case segmentation/evaluation comparison artifacts remain preserved. No Validation/Testing inference or baseline continuation occurred in this run.
- **M3:** Controlled synthetic candidate extraction was extended to allow declared phantom axes, bounded noise, multiple known narrowings and opt-in test-only geometric ground truth. The default/API sample remains free of target-geometry labels. Detection now uses the declared synthetic axis, a robust radial-area quantile profile and peak separation for multiple narrowings. A deterministic 180-phantom matrix (5 classes, 6 orientations, 3 noise levels, 2 replicates) measured precision 1.000, recall 0.9583, mean localization error 0.3574 axial voxels (median 0.3551), multiple-lesion recall 0.9375, and zero false candidates on 36 normal controls. Match tolerance: 2.8 axial voxels. These are generator-bound synthetic software checks, not real-vessel or clinical performance.
- **Frozen model evaluation:** A separate 500-phantom identity manifest uses disjoint 300/100/100 train/validation/test reservations (20 examples per class in each split), unique input hashes, and zero hash overlap with the existing checkpoint's training inputs. The existing checkpoint was evaluated but not changed or retrained. On the new 100-case synthetic test split, model macro-F1 was 0.2887 (accuracy 0.30); the synthetic geometry baseline macro-F1 was 0.9594 (accuracy 0.96). The baseline has access to generator-specified synthetic axis/geometry, so it is an oracle-like synthetic comparator, not a fair deployment baseline. This confirms the frozen CNN is not a useful classifier. No result supports patient generalization.
- **M4 / integration:** The synthetic workbench at `/research/experimental-stenosis` was exercised against an isolated migrated SQLite QA database and actual local FastAPI/React browser servers with temporary Researcher and Clinician accounts. Available-checkpoint and unavailable-checkpoint runs both passed; invalid payloads returned 422 and Clinician access returned 403. Results/export showed both authorization flags false. This was not PostgreSQL verification and did not modify staging.
- **Release:** Milestone 3 remains partial. Expert lesion-level supervision, clinical validation, a patient-volume predictor, clinical severity/percent narrowing, calibrated confidence and clinical XAI are unavailable. `clinical_gate_authorized=false` and `training_release_authorized=false` remain enforced.

Run evidence and artifact paths are listed in `TEST_EVIDENCE.md`; detailed synthetic algorithm/evaluation notes are in `docs/milestone3-research-completion.md`.


## Final M3 integration verification ? 25 November 2026

Current-source regression evidence: backend 997 passed / 198 skipped / 2 warnings; frontend 662 passed; full browser 221 passed / 4 explicitly gated skips; lint and build exited 0. The exact logs and skip reasons are in `TEST_EVIDENCE.md`. The earlier narrow-viewport evaluation failure was not reproduced. This audit does not recertify M1, M2 or M4. M3 remains a synthetic-only research demonstration, not clinically complete.

## 25 Nov 2026 — separate real-volume research QC increment

An authenticated, non-persistent endpoint was added at `POST /api/v1/experimental-stenosis/real-volume/analyze`. It accepts only a 3D `.nii`/`.nii.gz` CT and a matching binary 0/1 segmentation mask; both are size-bounded and validated for complete NIfTI payload, finite voxel values, equal dimensions, valid affines, affine alignment and compatible declared units. Temporary upload files are deleted after processing. The response records CT and mask-file SHA-256, native shape/orientation/spacing, RAS-mm spacing and a CT-bound geometry fingerprint when CT units support conversion.

The response reports foreground voxel/component counts and, only for physical geometry and masks no larger than 4 million voxels, attempts the existing conservative experimental branch-graph extractor. The graph may abstain on topology, thinning or support checks; it is a digital skeleton diagnostic, not a validated anatomical centerline. The general input cap is 67,108,864 spatial voxels; automatic graph extraction has the stricter 4,000,000-voxel cap.

Crucially, uploaded mask semantics are not source-attested. The ImageCAS audit identifies coronary artery segmentation masks, not lumen or lesion labels, and records unresolved mask units. Therefore the API returns no lesion candidates, no cross-sectional lumen profile, null reference/minimum lumen measurements, null percentage narrowing and null provisional severity. It never calls the synthetic CNN or Grad-CAM, persists no case/result, and enforces `clinical_validation=false`, `clinical_gate_authorized=false`, `training_release_authorized=false`. This completes a bounded real-volume input/QC and topology demonstration only; stenosis detection and measurement remain unavailable until a suitable source and its lumen semantics are independently verified.

Fresh checks: backend focused tests **17 passed, 1 skipped** (optional synthetic Torch-runtime test); frontend unit suite **664 passed**; focused browser workflow **5 passed**; Python compile, frontend production build, lint and staged/unstaged `git diff --check` exited 0. Lint reported three existing warnings (AuthContext and synthetic page); build reported the existing large NIfTI/runtime chunks. Browser testing used mocked API responses; API tests used temporary NIfTI fixtures and role dependency overrides, not a live database. No original dataset file, patient data, staging, database, model checkpoint, or Docker resource was accessed. The 164 staged paths, branch and HEAD were preserved; no files were staged or committed.

Final verification addendum (25 Nov 2026): after adding authorization-change invalidation coverage, the focused browser suite completed **6/6 passed**. The full application OpenAPI was generated under temporary test-only settings with warnings treated as errors and included `POST /api/v1/experimental-stenosis/real-volume/analyze` with unique operation ID `analyze_real_volume_research_upload`. The backend focused result remains **17 passed, 1 skipped**; the skip is the optional synthetic PyTorch runtime check. No patient, staging or production database was connected.
