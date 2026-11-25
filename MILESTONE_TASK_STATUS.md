# Milestone task checklist

## M3 geometry-measurement validation — 25 November 2026

- [x] Build reproducible controlled synthetic benchmark with separate generator
  ground truth; estimator receives no truth radii, lesion classes or truth labels.
- [x] Evaluate reference radius, minimum radius, percentage narrowing, localization,
  candidate detection and provisional threshold-category agreement.
- [x] Exercise normal, single/multiple lesions, six orientations, three noise levels,
  parameter boundaries and independent benchmark-held truth.
- [x] Add request threshold validation and UI display/export provenance; the UI
  explicitly shows measurement confidence and uncertainty as unavailable.
- [ ] No clinical thresholds, confidence calibration, physical measurement validation,
  expert labels, clinical review, or clinical/training authorization.
- [ ] General M3 stenosis detection/classifier and clinical validation remain blocked.

Frozen CNN was preserved separately (SHA-256
`a264d54a1fb4c370673ecaa7f8d3733982c0132b6e88e83dab1993cabb497937`); its distinct
held-out synthetic evaluation reported macro-F1 0.2887. This weak synthetic result
is not evidence for clinical inference and is not combined with the geometry benchmark.

Result artifact: `F:\vascuai-artifacts\runs\m3-synthetic-geometry-measurement-20261125T093700Z\measurement-benchmark.json` (deterministic repeat `T094000Z`, identical SHA-256).
180 phantoms / 216 lesions; recall 0.9583, precision 1.0; profile percentage MAE
2.2917 percentage points (max error 13.0818); localization MAE 0.3574 axial voxels,
signed bias +0.0139 axial voxels.
All figures are synthetic-generator-specific and not clinical performance claims.

Final audit: synthetic-only Milestone 3 workflow may be demonstrated with explicit
limitations. Clinical patient workflow, expert supervision, calibrated confidence,
clinical severity, real-image validation and patient-integrated XAI remain blocked.
M1/M2/M4 were regression-tested but not recertified by this audit.

---

## Final engineering checklist

Updated 24 November 2026. Evidence: `final-engineering-20261124T093721Z`.
Branch `codex/milestone3-review`; HEAD remains `e37b7c87eebe5099686687eacd6a6db897d2e6c7`.
At report time, changes were local and unstaged. The later preflight staged all 164 pending paths locally; no commit, push, merge, staging migration or deployment has occurred.

- [x] M1 current foundation, architecture/wireframes and final documentation.
- [ ] Historical Week 1 evidence and mentor sign-off not independently established.
- [x] M2 completed and freshly reproduced 50-case/model comparison; 100 masks verified.
- [x] M3 automatic admitted-tree-to-profile bridge + explicit native-file CLI.
- [x] M3 14 synthetic geometries and independent endpoint/branch/spatial checks.
- [x] M3 original refusal rules preserved; refused inputs produce no sampling plan.
- [x] M3 current-source polling and 4,276,737-voxel synthetic API/browser integration.
- [ ] M3 general automatic centerlines unresolved; 4 admitted / 14 tested.
- [ ] M3 clinical model/labels/severity/confidence/stenosis attribution unavailable.
- [x] M4 embedded third-reader CT-only viewer and verified source/parent loader.
- [x] M4 source/protocol-linked documentation counts and eligible SQL pagination.
- [x] M4 original immutable R1/R2/submission/adjudication history retained.
- [ ] M4 full packet/evidence receipts and real protocol/qualification/independence sign-off.
- [x] M4 append-only owner-private amendment chain; amendments and R3 assignment are
  refused in either order under the current adjudication contract.
- [ ] M4 amendment-aware adjudication, assignment withdrawal/reassignment, full packet
  receipts, and real qualification/independence sign-off.
- [x] Full available PG/browser/scientific/frontend and focused actual-API tests.
- [x] Fresh synthetic 0015 schema restore; SQLite fallback cleanup safely corrected.
- [ ] Fresh operational staging backup/restore and approved deployment of latest source.

Both release flags remain false. No unverified review or algorithmic agreement is
clinical ground truth. See latest M3 matrix and evidence report for exact scope.

---

## Prior entries (preserved)

## Latest milestone checkboxes ? 24 November 2026

- [x] M1: implemented foundation and portable documentation retained; final HTML/PDF created.
- [ ] M1: historical Week 1 evidence / mentor sign-off remains unverified.
- [x] M2: verified 50/50 baseline and 50/50 SegResNet comparison remains unchanged.
- [x] M3: bounded offline supplied-branch profiles, R1/R2 procedures and R3 disagreement trace.
- [x] M3: authenticated offline browser import verifies actual stored CT/mask and entire profile.
- [x] M3: source navigation, read-only workspace export/restore, normal-export isolation tested.
- [ ] M3: reliable automatic extraction not established; one/eight new probes admits a tree.
- [ ] M3: suitable lesion supervision / trained stenosis model / validated severity or XAI absent.
- [x] M4: manual draft, assignment isolation, immutable submission and adjudication preserved.
- [x] M4: fresh available PostgreSQL/browser regressions; new actual-API research rehearsal.
- [ ] M4: real qualification, full packet/evidence-receipt operations and amendments remain partial.
- [ ] M4: current-schema real backup/restore, approved images/migrations/release and deployment pending.

Both authorization flags remain false. No migration/gate/staging operation was made.
Current requirement-to-code-to-test details: docs/offline-research-evidence.md and
latest entry in docs/milestone3-research-completion.md. The current increment is
m3-browser-centerlines-20261124T082756Z; earlier entries below are historical.

---

## Historical entries (preserved)

Updated 24 November 2026 11:14 IST. Local increment `m3-completion-20261124T051538Z`; branch/HEAD unchanged. No commit, push, merge, staging migration or deployment.

## Latest milestone checkbox progress

- [x] M1 foundation/documentation deliverables preserved; historical design evidence
  and mentor sign-off remain external.
- [x] M2 completed 50-case comparison/checkpoints preserved; its documented protocol,
  native-unit and automatic-centerline research limits remain.
- [x] M3 supported offline native-mask processing, source binding, supplied-branch
  candidates, research measurements, replay, localization and visual evidence implemented.
- [x] R1/R2 definitions preserved; R3 retains disagreements without majority labels.
- [x] Full available PostgreSQL and browser regressions rerun; previously stopped QA
  target was safely restarted and actual-API reviewer rehearsal passed.
- [ ] M3 fully automatic branches/full-size browser integration remain incomplete.
- [ ] Stenosis model training, validated severity/localization/percentages and genuine
  stenosis XAI remain blocked by absent suitable supervision/model/clinical evidence.
- [ ] Qualified expert reviews and clinical/training release remain unavailable.
- [x] M4 annotation/submission/adjudication implementation and migrations preserved.
- [ ] M4 current-schema backup/restore, approved release, staging rehearsal and deployment
  remain separate outstanding operations. No staging action was performed.

Requirement-level classifications and implementation/test references are in
`docs/milestone3-research-completion.md`. Local hash-linked research files do not
become trusted server attestations, human submissions, evaluation metrics or labels.
All 122 pre-existing changed paths were retained; only the documented increment
was edited/added. Both authorization flags remain false.


---

## Prior sprint evidence (historical, preserved)

Updated 24 November 2026 10:15 IST. Evidence: external run `ai-assisted-m3-20261124T042751Z`. Branch and HEAD unchanged. All new work remains local, unstaged and undeployed.

## Current M3 implementation checklist

| Official task | Current state | Current evidence / remaining limitation |
|---|---|---|
| Stenosis detection pipeline | Partial research | Existing supplied-centerline sampler plus new two-procedure workbench; no validated clinical detector |
| Candidate regions | Partial / demonstrated | Source-bound region intervals and support; actual synthetic backend outputs verified; automatic full-volume branches remain unresolved |
| Train classifier/detector | Blocked | No verified authorized lesion-level supervision; no pseudo-label training |
| Localization | Partial / demonstrated | Native IJK/RAS centers, bounds and CT navigation; artery identity stays null |
| Severity classification | Unavailable | No model or expert labels; no automatic severity assignment |
| Estimated narrowing | Partial research only | Documented equivalent-diameter reduction and explicit supported caliper arithmetic; not a validated clinical output |
| Explainable AI | Unavailable for stenosis | Geometric trigger/support evidence available; no stenosis model target or fabricated Grad-CAM |
| Visualization | Partial / demonstrated | Separate research card, candidate navigation and unverified tables in prediction viewer |
| AI analysis dashboard | Partial | Local provisional source/procedure/status/disagreement display; not an AI reviewer service or clinical dashboard |

- [x] New standalone research JSON is source-bound, recomputed on restore/export,
  rejects altered content/flags and cannot enter normal reports.
- [x] R1 and R2 procedures do not consume each other's results; R3 retains both.
- [ ] Statistical independence, expert qualification and clinical validity are not established.
- [ ] Durable authenticated simulated-agent history is not implemented; local checksums
  are tamper-evident, not trusted server attestations.
- [x] Both clinical and training authorizations remain false, including R3.
- [x] M1 foundations/docs and completed M2 comparison preserved.
- [x] Existing M4B/C/D production source and migrations preserved byte-for-byte.
- [ ] Current PostgreSQL rerun blocked by the stopped disposable QA container.
- [ ] Staging release remains unapproved and undeployed; no new backup/migration.

The new path retains the 4-million-mask-voxel/2-MiB document bounds and existing
viewer geometry/resource refusals. It does not demonstrate automatic analysis of
typical full-size original CT masks. No Validation cases were used for training,
no Testing data were modified and no real expert labels were generated.


---

## Previous completed sprint evidence (retained; not a fresh rerun)

Updated 24 November 2026 09:41 IST. Branch `codex/milestone3-review`; base HEAD `e37b7c87eebe5099686687eacd6a6db897d2e6c7`. New code is uncommitted and undeployed. External evidence run: `completion-sprint-20261123T171203Z`.

## M1 - foundations/documentation

- [x] Existing objectives, coronary CTA workflow, dataset/splits, schema, frontend,
  backend, authentication, cases, upload and preprocessing retained/tested.
- [x] Architecture verified; portable as-implemented wireframes added.
- [ ] Original Week 1 design evidence not found in inspected source; current artifact
  is clearly a reconstruction. Mentor sign-off remains external.

## M2 - segmentation/vessel analysis

- [x] Baseline finished, 50/50 usable predictions; original two cases reused.
- [x] Existing SegResNet training/checkpoint/50-case evaluation preserved.
- [x] Exact 50-case cohort verified: 100 masks, original reference hashes/grids/counts.
- [x] Reproducible per-case comparison, macro denominators, pooled micro separation,
  thresholds, grid differences and provenance limitations recorded.
- [x] Higher observed SegResNet Dice documented for this cohort, not as clinical validation.
- [x] Vessel/supplied-centerline candidate regressions: 84 passed.
- [ ] Baseline original training-run identity/verified optimizer count unresolved.
- [ ] Reliable arbitrary-3D automatic branches remain experimental; source-support/
  skeleton-loss limits unresolved. No matrix/instrumentation rerun or tuning.
- [ ] Surface distances/ROC-AUC are not invented from masks/counts; appropriate
  spatial-unit/alignment and score protocols remain necessary.

## M3 - stenosis research

- [x] Source-bound candidate previews, unavailable states and fail-closed exports retained.
- [x] Manual review preparation/visualization progressed; automatic research wrappers
  cannot enter ordinary report JSON.
- [x] 401/402/404 packet: 44 files and 15 source assets rehashed unchanged.
- [ ] Validated automatic stenosis detection/localization not established.
- [ ] Qualified clinical lesion supervision unavailable; classifier training blocked.
- [ ] Validated severity/percentage and genuine stenosis XAI remain unavailable.
- [ ] Clinical and training release remain disabled, including after adjudication.

## M4 - review/integration/release

- [x] Existing case/patient/upload/viewer/evaluation/comparison/history/reporting retained.
- [x] 4A CT-only viewer isolation and source/geometry safeguards preserved.
- [x] 4B core: manual landmarks/evidence/nulls, source-bound private revisions and JSON.
- [x] Resource-limited CT supports verified download/manual IJK without raising caps;
  checksum/geometry failures still withhold the worksheet.
- [x] 4C immutable independent submissions/idempotency/concurrency implemented.
- [x] 4D core third-account assignment, correspondence/discrepancy resolution,
  unresolved outcomes, historical access and immutable finalization implemented.
- [ ] Full external expert-packet inventory/mapping, evidence receipts, coverage and
  protocol/qualification signoff integration remain partial; no dummy credential bypass.
- [ ] Versioned amendments/reassignment/withdrawal and embedded third-reader CT absent.
- [x] Migration tests, synthetic custom dump/disposable restore, full available
  backend/browser, actual-API reviewer tests, build/lint passed.
- [x] Read-only staging/backup checks: health 200, schema 0010; backup integrity and
  private ACL valid but backup schema 0009 is stale.
- [ ] Fresh coordinated real DB/private-storage backup and restore requires approved
  tooling/window and confirmed paused writers.
- [ ] Release identity/images, migrations 0011-0015, staging rehearsal/deployment need approval.
- [ ] Old API rollback after assignments would remove blinding; compatible recovery required.
- [ ] Cloud/clinical production operation is not established by these local tests.

## Files/evidence/deployment map

| Task | Implementation/evidence | Blocker | New deployment verified |
|---|---|---|---|
| M1 | `docs/project-architecture.md`, `docs/ui-wireframes.html`, README | historical evidence/sign-off | No |
| M2 | external `baseline-continuation-20261124T032609Z`, `verify_comparison.py`, `comparison-50` | heterogeneous protocols, no independent clinical/test claim | No |
| 4B | review_annotation model/schema/service, migration 0013, ReviewAnnotationForm and review-annotation.js | full expert packet partial | No |
| 4C | review_submission model/service, migration 0014 | amendment process absent | No |
| 4D | review_adjudication model/schema/service/router, migration 0015, ReviewAdjudications.jsx | real qualified reviewer unavailable | No |
| M3 safeguards | exports.js and public reporting regressions | validated clinical model/labels absent | No |
| Release | four reports, external staging/backup/migration evidence | fresh backup and approvals | No |

All 114 pre-resume changed paths were preserved (34 tracked modifications, 80
untracked). No files were deleted to match a viewer count. Clinical requirements
that remain blocked are not marked complete.

## 2026-11-25 focused follow-up

| Task | Status | Evidence / limitation | Deployed |
|---|---|---|---|
| Structured stenosis research PDF | Implemented and locally tested | Authenticated report snapshot endpoint; synthetic zero-finding, candidate and status-only layouts verified; source report contains no image payload, so no CT/overlay image is embedded | No |
| Full UI/UX spacing and responsive cleanup | Partial / not audited end-to-end | Existing unit/e2e coverage is not a whole-app visual audit | No |
| Clinical stenosis model and validation | Blocked | No qualified lesion-level labels or validated model; safety gates remain disabled | No |

## Dataset supervision status - 2026-11-25

- [x] Compared primary-source dataset modality, annotation type, access conditions and visible license metadata for ASOCA, Zenodo 4638863 and ARCADE.
- [x] Confirmed ImageCAS/ImageCAS-X artery masks are not stenosis lesion labels.
- [ ] Obtain lawful access to a compatible 3D CTA lesion-level dataset and verify its terms/labels.
- [ ] Train/evaluate a lesion model on authorized lesion labels; no suitable real lesion data is currently available. The synthetic-only CNN is pipeline research evidence, not a real lesion model.

## 2026-11-25 synthetic-only model experiment

- [x] Implemented optional synthetic phantom generation, patient/sample-ID-separated train/validation/test splits, a 3D CNN training loop, validation-loss checkpoint selection, held-out metrics, checkpoint validation, synthetic-only inference and genuine 3D Grad-CAM: `backend/app/services/synthetic_stenosis_ml.py`.
- [x] Trained and evaluated one model on 500 generated phantoms in an isolated PyTorch CPU environment. Held-out synthetic accuracy 0.31, macro-F1 0.3076 over 100 test phantoms; this is weak and has no patient-generalization meaning.
- [ ] No real lesion-labeled dataset is available/authorized; no patient-case API or dashboard uses this classifier; no clinical severity, percentage, or stenosis Grad-CAM is enabled.
- [ ] General automatic centerline extraction remains limited and the separate bounded geometry workflow still requires explicit source-bound branches for its admitted cases.

## 2026-11-25 synthetic research UI/API integration

| Requirement | Status | Evidence / limitation |
|---|---|---|
| Separate synthetic experimental workflow | Partial | Authenticated `/research/experimental-stenosis` page and `/api/v1/experimental-stenosis/{status,samples,analyze}` endpoints; only deterministic bounded server-generated phantoms accepted. |
| Candidate localization and geometry summaries | Partial (synthetic only) | Candidate markers, profile plot and voxel-unit summary are rendered; no patient volume, RAS/mm measurements, or clinical result. |
| 3D CNN inference and Grad-CAM | Partial / optional | API requires externally configured checkpoint path and exact SHA; actual isolated TestClient tests passed, and the existing v5 artifact passed fresh hash/load/phantom inference/Grad-CAM smoke verification. It predicted `normal` on this generated sample; its 0.31 synthetic holdout accuracy is weak and not clinically useful. |
| Role boundary | Implemented in code; partially exercised | Admin/Data Scientist/Researcher route dependency; Clinician denied by focused browser flow; six direct isolated API/model tests passed. Normal app pytest collection still lacks `reportlab` in the worktree interpreter. |
| Research export / history | Partial | Local JSON download of current response only; no persistence or server-side history. |
| Clinical/training authorization | Safely unavailable | Response/checkpoint contracts hard-code false; never inferred from request; clinical output remains disabled. |

The CLI is `backend/scripts/train_synthetic_stenosis.py`. The checkpoint is an external run artifact, not a deployed model. The default API requirements, routes, database, clinical gate and training-release gate were not changed.

## Current verification update — 25 Nov 2026

- [x] M3 deterministic controlled synthetic detector tests across 5 generated classes, 6 axis orientations, 3 noise levels and multiple lesions; result: 180 cases, 1.000 precision, 0.9583 recall, 0.3574 mean axial-voxel localization error, 0 false candidates on 36 normal controls.
- [x] Separate reproducible 500-sample synthetic evaluation manifest with 300/100/100 disjoint reservations, balanced classes, unique hashes and zero overlap with frozen checkpoint training inputs.
- [x] Existing synthetic checkpoint reevaluated without modification: synthetic test macro-F1 0.2887; simple geometry baseline 0.9594 (uses generator geometry; not a fair clinical/deployment baseline).
- [x] Backend full available suite: 1006 passed, 197 skipped (PostgreSQL-only cases), 3 warnings. Frontend unit 658 passed; browser 221 passed/3 skipped; actual-API browser 2 configurations passed.
- [ ] M3 qualified lesion labels, clinical model, validated severity/percentage, calibrated confidence and clinical XAI remain blocked/unavailable.
- [ ] M4 PostgreSQL-backed reviewer concurrency suite was not rerun in this SQLite-only test environment; staging backup/restore and deployment were not attempted.

M1/M2 prior accepted evidence and all prior M4 changes are preserved; they were not rerun as a separate milestone certification in this increment. Both authorization flags remain false.


## Final integration audit ? 25 November 2026

M3 implementation status remains **partial (synthetic-only)**. The final current-source run recorded backend 997 passed / 198 skipped / 2 warnings, frontend 662 passed, browser 221 passed / 4 gated skips, and lint/build exit 0. See `TEST_EVIDENCE.md` for exact evidence and environment limitations. Clinical lesion labels, calibrated confidence, validated physical measurements, patient-image performance and clinical authorization remain missing. M1/M2/M4 were regression-tested but not recertified.

## 25 Nov 2026 — separate real-volume research QC increment

An authenticated, non-persistent endpoint was added at `POST /api/v1/experimental-stenosis/real-volume/analyze`. It accepts only a 3D `.nii`/`.nii.gz` CT and a matching binary 0/1 segmentation mask; both are size-bounded and validated for complete NIfTI payload, finite voxel values, equal dimensions, valid affines, affine alignment and compatible declared units. Temporary upload files are deleted after processing. The response records CT and mask-file SHA-256, native shape/orientation/spacing, RAS-mm spacing and a CT-bound geometry fingerprint when CT units support conversion.

The response reports foreground voxel/component counts and, only for physical geometry and masks no larger than 4 million voxels, attempts the existing conservative experimental branch-graph extractor. The graph may abstain on topology, thinning or support checks; it is a digital skeleton diagnostic, not a validated anatomical centerline. The general input cap is 67,108,864 spatial voxels; automatic graph extraction has the stricter 4,000,000-voxel cap.

Crucially, uploaded mask semantics are not source-attested. The ImageCAS audit identifies coronary artery segmentation masks, not lumen or lesion labels, and records unresolved mask units. Therefore the API returns no lesion candidates, no cross-sectional lumen profile, null reference/minimum lumen measurements, null percentage narrowing and null provisional severity. It never calls the synthetic CNN or Grad-CAM, persists no case/result, and enforces `clinical_validation=false`, `clinical_gate_authorized=false`, `training_release_authorized=false`. This completes a bounded real-volume input/QC and topology demonstration only; stenosis detection and measurement remain unavailable until a suitable source and its lumen semantics are independently verified.

Fresh checks: backend focused tests **17 passed, 1 skipped** (optional synthetic Torch-runtime test); frontend unit suite **664 passed**; focused browser workflow **5 passed**; Python compile, frontend production build, lint and staged/unstaged `git diff --check` exited 0. Lint reported three existing warnings (AuthContext and synthetic page); build reported the existing large NIfTI/runtime chunks. Browser testing used mocked API responses; API tests used temporary NIfTI fixtures and role dependency overrides, not a live database. No original dataset file, patient data, staging, database, model checkpoint, or Docker resource was accessed. The 164 staged paths, branch and HEAD were preserved; no files were staged or committed.

Final verification addendum (25 Nov 2026): after adding authorization-change invalidation coverage, the focused browser suite completed **6/6 passed**. The full application OpenAPI was generated under temporary test-only settings with warnings treated as errors and included `POST /api/v1/experimental-stenosis/real-volume/analyze` with unique operation ID `analyze_real_volume_research_upload`. The backend focused result remains **17 passed, 1 skipped**; the skip is the optional synthetic PyTorch runtime check. No patient, staging or production database was connected.
