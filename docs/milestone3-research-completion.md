# Milestone 3 research completion increment

## Official Milestone 3 requirement audit — 25 November 2026

The official specification is the project PDF supplied by the owner. Status below
distinguishes a bounded synthetic research demonstration from the expected patient
image/clinical outcome. Evidence for the current increment is under
`F:\vascuai-artifacts\diagnostics\m3-measurement-validation-20261125\`; the
deterministic measurement result is
`F:\vascuai-artifacts\runs\m3-synthetic-geometry-measurement-20261125T093700Z\measurement-benchmark.json`.

Final regression rerun on 25 November: backend **997 passed, 198 skipped, 2
warnings** (exit 0); frontend **662 passed** (exit 0); full browser **221 passed,
4 skipped** (exit 0); lint and production build exit 0 with warnings documented in
`TEST_EVIDENCE.md`. The four browser skips are two PostgreSQL acceptance tests, one
explicit live-API credential opt-in, and one real-volume path opt-in. This run did
not exercise PostgreSQL concurrency or Torch/Grad-CAM runtime; skipped tests are
not passes. The prior narrow-viewport evaluation failure did not reproduce.
Milestones 1, 2 and 4 were not recertified by this audit.

| Official Milestone 3 item | Audit status | Evidence and remaining gap |
|---|---|---|
| Develop stenosis detection pipeline | **Partial — synthetic only** | Separate authenticated `/api/v1/experimental-stenosis` workflow runs geometry estimation and an optional synthetic CNN. It never accepts a patient case. No validated patient-image detector exists. |
| Extract stenosis candidate regions | **Partial — synthetic phantom only** | Synthetic cross-sectional profile extraction finds candidate intervals. General artery-mask/centerline extraction is not established; previous automatic-branch review records abstentions and supported-input limits. |
| Train stenosis classification/detection model | **Partial — synthetic-only CNN** | A frozen synthetic 3D CNN/checkpoint and disjoint synthetic evaluation exist. Separate held-out synthetic macro-F1 was 0.2887; this is weak and not real lesion supervision. No expert-labelled classifier is available. |
| Stenosis localization | **Partial — generated axis only** | Coordinates and match error are evaluated against phantom truth; method uses a generator-provided axis, not automatic anatomical localization. No patient lesion localization is validated. |
| Severity classification | **Blocked clinically; provisional software only** | Configurable 10/30/50/70% buckets are clearly synthetic/research-only. The specification says clinical thresholds must derive from a validated reference standard. No such labels or standard were supplied. |
| Estimated percentage narrowing | **Partial — synthetic geometry only** | Area-equivalent-radius estimates and percent formula are benchmarked in synthetic voxel units. No calibrated physical units, anatomical reference selection, or clinical accuracy is established. |
| Model confidence | **Unavailable** | Geometry measurement confidence/uncertainty are null. CNN softmax is explicitly uncalibrated, not clinical confidence. |
| Explainable AI / Grad-CAM | **Partial — synthetic checkpoint only** | 3D Grad-CAM implementation produces a source-bound phantom heatmap. PyTorch-dependent tests were skipped in the current environment; prior synthetic API evidence is historical. No patient stenosis attribution or independently assessed explanation is available. |
| Original image + artery mask + stenosis region + model explanation | **Partial** | A synthetic phantom workbench visualizes the generated input, profile, candidate interval and optional synthetic Grad-CAM. The full combined workflow is not integrated into the patient CT viewer. |
| AI analysis dashboard | **Implemented for isolated synthetic research** | React page exposes sample generation, validation/errors, measurements, candidate summaries, model state, Grad-CAM when available and JSON export. This is not the clinical dashboard outcome. |
| Detection/severity evaluation metrics | **Partial — synthetic only** | Geometry benchmark reports candidate precision/recall and measurement errors; synthetic CNN evaluation is separate. No expert-labelled stenosis test set, clinical sensitivity/specificity/AUROC/FPR/FNR, or external validation exists. |
| Reports and traceability | **Partial** | Dedicated JSON export carries source/checkpoint/method/threshold provenance and false authorization flags. No patient stenosis report, stenosis PDF/CSV or persisted result is produced by this workflow. |
| Integrate results into patient cases/clinical reports/normal analytics/training | **Intentionally not implemented** | The route is separate and non-persistent, rejects case fields, and response contracts reject ground-truth labels. No import into case, report, analytics, or training pipelines exists. Synthetic training uses generator labels directly in its separate offline experiment; analysis outputs are not fed back into training. |
| No fabricated clinical findings / clinical readiness | **Pass for current safety boundary** | Both authorization flags remain false; no clinical labels, patient scans, predictions, or clinical claims are generated by this workflow. |

| Official performance metric | Current evidence/status |
|---|---|
| Stenosis candidate precision / recall | Synthetic geometry-only: 1.000 / 0.9583 on 180 generated profiles; not patient detection performance. |
| CNN accuracy / macro precision / macro recall / macro-F1 | Separate frozen-CNN synthetic test: 0.30 / 0.2951 / 0.30 / 0.2887 on 100 generated phantoms. Weak and not clinical. |
| Per-class F1 / confusion matrix | Present in the separate synthetic evaluation artifact; no expert-labelled stenosis classes. |
| Severity accuracy / macro-F1 | Provisional synthetic threshold categories only: 0.9855 / 0.9872 matched candidates. Category construction shares the generator thresholds and is not independent clinical classification. |
| Sensitivity, specificity, AUROC, false-positive/false-negative rates | Not reported as validated stenosis metrics. Existing synthetic artifacts do not establish these clinical criteria. |
| Weighted F1 | Not reported in the current synthetic evaluation artifact. |

### Endpoint, provenance and estimator boundary

`GET /status`, `POST /samples`, and `POST /analyze` require Admin, Data Scientist,
or Researcher roles; tests verify unauthenticated 401 and Clinician 403. Requests
are strict and bounded. They carry only synthetic generation parameters and reject
case IDs or arbitrary source volumes. The sample and analysis schemas are v0.2/v0.3;
recursive response validation blocks class labels and benchmark truth fields. Sample
and analysis output includes no synthetic class truth, patient/case association, or
benchmark geometry truth. The CNN receives the generated volume tensor; the class
parameter is used to generate/reproduce a controlled phantom, not appended as a
prediction feature. The geometry estimator receives the synthetic input/provenance;
the benchmark removes truth radii, lesion labels and truth coordinates before
calling it. Tests compare estimator output with and without opt-in truth metadata.

The benchmark now uses maximum-cardinality, minimum-distance one-to-one assignment
within 2.8 axial voxels, not greedy pairing. MAE/RMSE use signed estimate-minus-truth
errors; bias is their signed mean; p50/p90/max are absolute-error quantiles. A
regression test covers a greedy counterexample and another verifies signed bias.
The deterministic repeat artifact is
`F:\vascuai-artifacts\runs\m3-synthetic-geometry-measurement-20261125T094000Z\measurement-benchmark.json`;
it is byte-identical to the primary result (SHA-256
`BBC6BC6C4E1FDB74032B85BF1C574BDBDC800F1D09A2CE3FED7810C92274F331`).

### Overall determination

Milestone 3 is **not complete against the official clinical-oriented requirements**.
The isolated synthetic software is suitable only for an explicitly synthetic
internship demonstration, with its limitations shown. Expert lesion supervision,
qualified review, real-image performance, calibrated measurements/confidence,
clinically defined thresholds, validated localization and patient-integrated XAI
remain unavailable. Do not represent the provisional categories as clinical
severity. This audit does not recertify Milestones 1, 2 or 4; their earlier evidence
remains historical, with current regression evidence recorded separately in
`TEST_EVIDENCE.md`.

---

## Final engineering sprint — 24 November 2026

Evidence run: `final-engineering-20261124T093721Z`. Same review branch/base HEAD;
all changes remain local/unstaged. Both release flags remain false.

| Requirement | Latest implementation / actual evidence | Remaining limitation |
|---|---|---|
| Automatic branches | Guarded native-file CLI and retained-tree-to-profile bridge; 14 analytic geometries, integrity and invalid-input tests | 4 admitted / 14; source-support/even-width/ambiguous inputs abstain; general extraction unproven |
| Topology / spatial validation | Complete raw-edge/vertex partition, independent endpoint-pair branch matching, displacement/endpoints/coverage and zero false/missing matches for admitted controls | Synthetic discretization-scale evidence, not anatomical accuracy; no pruning or guard relaxation |
| Bounded browser delivery | Actual-API small + 4,276,737-voxel synthetic CT workflow; mask remains server-side | Not a maximum-size or original clinical-volume benchmark |
| Idle-source freshness | Private actual-mask-byte identity GET, focus/60-second checks; post-hash session and DB metadata recheck | Periodic freshness is not continuous revocation or distributed resource enforcement |
| M2 preservation | Fresh 100-prediction/50-case comparison verification; all 53 comparison artifacts match previous | Protocol/training/grid/threshold confounding and unknown reference units remain |
| M4 integration | Embedded third-reader original CT, verified loader, source/protocol documentation counts, SQL credential filtering | Real qualification/packet sign-off and versioned amendment/reassignment/withdrawal remain incomplete |
| Tests | 649 frontend; 874 PostgreSQL passed/13 skipped; 211 scientific; 216 browser passed/3 skipped; 25 API; 3 actual-API workflows; 76 SQLite passed/3 skips; synthetic restore 1 | Suites overlap; optional/model/platform/explicit opt-ins documented |
| Release | Live read-only health 200, unauthorized protected reads 401, current schema 0010 and old images confirmed | Old 0009 backup is stale; no approved current backup/migration/deployment |

See [automatic branch workflow](automatic-branch-research.md) and
[offline browser evidence](offline-research-evidence.md). M3 remains partial:
no qualified lesion labels, trained stenosis classifier, validated severity,
calibrated confidence or genuine stenosis attribution exists.

---

## Latest extension — 24 November 2026

External evidence: `m3-browser-centerlines-20261124T082756Z`. Local only; same
branch/HEAD. Earlier dated evidence below is preserved as historical context.

| Requirement | Current implementation | Fresh evidence / limit |
|---|---|---|
| Offline browser evidence | Versioned literal plan + actual profile; authenticated server recomputes against stored CT/prediction and rechecks session/source | 22 PostgreSQL API tests, including blinded-reader 403; exact fields/code/environment comparison |
| Browser resource separation | Separate read-only panel; no full-mask download; optional source CT only | 2 new browser tests and 1 actual-API browser rehearsal; original CT/GPU/geometry budgets retained |
| R1/R2/R3 integration | Shared assessment constructor accepts only fresh transport receipts; deterministic procedures and disagreements | 636 frontend suite; forged receipt/response, changed source/session and replay checks |
| Research export/restore | Read-only workspace; fresh server verification and deterministic assessment hash on export/restore | Actual-API round trip; ordinary public JSON helpers reject all offline wrappers |
| Automatic extraction | Existing algorithm/guards unchanged; new small characterization only | 8 probes deterministic/source-preserving; Y accepted, 7 abstain; no general reliable method established |
| Native processing / geometry | Bounded sampler and producer preserved; browser envelope added | 178 isolated scientific regressions; no frozen 20-case matrix/instrumentation rerun |
| Integration/security | Existing role/case/assignment isolation retained; no new DB/persistence/gate | Full available PostgreSQL 868 passed/12 skipped; complete browser 213 passed/3 skipped |
| Final documentation | Standalone website-themed HTML and searchable A4 PDF with evidence/limits | Rendered document, internal navigation, embedded resources and mobile overflow checks |
| Clinical M3 outputs | Still unavailable | No suitable expert supervision, classifier, severity, calibrated confidence or stenosis attribution |

See [offline evidence procedure and limitations](offline-research-evidence.md).
The declaration of Training membership in an offline plan is not a dataset/licence
attestation. Multi-worker rate/resource control and hard CPU deadlines are not
established by the one-per-process verification semaphore. Exact environment/code
binding intentionally rejects incompatible producer artifacts. No clinical/training
authorization or deployment is introduced. M3 remains partial.

---

## Prior increment (preserved)

Date: 24 November 2026. Branch `codex/milestone3-review`, HEAD
`e37b7c87eebe5099686687eacd6a6db897d2e6c7`. Local uncommitted source only.
Evidence run: `m3-completion-20261124T051538Z` outside Git.

## Requirement → implementation → evidence

| Requirement | Classification / status | Code and actual verification |
|---|---|---|
| Bounded candidate processing | Implemented for supported offline inputs | `tiled_candidate_profile.py`, `research_candidate_profile.py`; whole-mask hash/connectivity plus mapped gathers; 4,276,737-voxel NIfTI demo and parity/negative tests |
| Native anisotropic/oblique geometry | Implemented offline; browser remains bounded | Exact CT/plan/mask numerical geometry checks, original coordinates; oblique/anisotropic/invalid-unit tests; no registration claim |
| Automatic reliable branches | Not established by available algorithm/evidence | Supplied ordered branches remain mandatory; previous skeleton/source-support research is preserved, not replaced with a weak heuristic |
| R1/R2/R3 definitions/replay | Implemented research only | Definitions unchanged; six backend-generated boundary profiles, inclusive trigger/reference-window/contiguous-support tests, deterministic replay and tamper tests |
| Localization/navigation | Implemented for supported viewer data | Candidate/sample navigation checks source snapshot and native IJK/RAS; actual NiiVue tests cover two distinct locations; unsupported oblique browser geometry still refuses |
| Research measurement | Implemented arithmetic only | Explicit affine endpoint distances/formula, positive lengths, bounds, nulls, inverted-reference/shear/unit refusal; no anatomical reference validation |
| Explainability evidence | Implemented geometric trace | `ResearchEvidence.jsx`/`research-evidence.js`: profiles, support windows, raw triggers vs accepted regions, gaps, disagreement and accessible numeric table; UI/axe tests |
| Stenosis Grad-CAM/confidence | Blocked by absent suitable prediction model | No stenosis logits or calibrated confidence exist; geometric trace is not model attribution |
| Stenosis classifier/severity | Blocked by missing verified lesion supervision | No expert/pseudo labels, training or severity grades generated; Validation/Testing not repurposed |
| Expert annotation/clinical approval | Requires qualified human evidence and separate authorization | No reviewer credentials seeded; no clinical/training authorization, even after adjudication |
| Research export/security | Implemented local boundary | Restore replays source/procedures; both ordinary JSON paths reject research wrappers/derived rows; human schemas and evaluation metrics reject research objects; no new training importer |
| Trusted durable AI submissions | Not implemented / not claimed | In-memory freeze and downloadable hash-linked evidence only; human immutable submission system remains separate |
| PostgreSQL/security integration | Freshly verified | Pinned disposable QA restarted; 868 passed/10 skipped; actual-API reviewer rehearsal 1 passed; staging untouched |

## Fresh test results and commands

Counts overlap; they are not a total of distinct requirements or clinical cases.

- Frontend `npm test`: **622 passed**, exit 0. Includes 50 public research helper tests.
- `npx playwright test --workers=1`: **211 passed, 3 skipped**, exit 0.
  Two skips require a configured stenosis provider; the third is the opt-in supplied
  real-volume test. No opt-in safeguard or assertion was removed.
- Disposable PostgreSQL suite: **868 passed, 10 skipped**, exit 0. Missing optional
  Torch/MONAI, Windows symlink privilege and explicit live/restore opt-ins explain
  the skips. Actual-API reviewer browser test was separately run: **1 passed**.
- Offline research command, from `backend`:

```text
python -B -m pytest --noconftest -q --tb=short tests/test_tiled_candidate_profile.py tests/test_research_profile_cli.py tests/test_experimental_candidates.py tests/test_research_profile_evidence.py
```

  **119 passed**, exit 0. Uses the existing SciPy research environment, not an
  application database. All existing serialized small-profile outputs still match.
- PostgreSQL command uses the pre-existing safety-checked disposable QA runner:

```text
python -B run_disposable_tests.py --ignore=tests/test_automatic_branches.py --ignore=tests/test_experimental_candidates.py --ignore=tests/test_vessel_analysis.py --ignore=tests/test_research_profile_evidence.py -o faulthandler_timeout=60
```

  Collection preceded creation of the two new SciPy-only test modules. Future runs
  in the backend environment must also ignore `test_tiled_candidate_profile.py` and
  `test_research_profile_cli.py`, or use an environment providing SciPy. Those tests
  were run separately; no dependency or lockfile was modified.
- `npm run build`, `npm run lint`, `git diff --check`: exit 0. Existing large-chunk
  and AuthContext Fast Refresh warnings remain.

## Failure paths exercised/corrected

The first research invocation used the repository root without backend on Python's
import path; rerunning from backend fixed collection. The mapped-volume test initially
passed a dict to an existing typed geometry helper; the test now validates its real
geometry object. A fixture generator initially referenced the wrong existing helper;
only its newly created empty output was populated after correction. No prior fixture
was replaced. A new axe check found invalid ARIA on SVG polylines; semantic SVG titles
and the parent image label fixed it without disabling the assertion.

Further negative tests cover source changes during execution, non-native rounded
geometry, unknown units, gzip expansion, collisions, oversized storage/frontiers,
invalid branch identities, scalar parameter types and numeric over/underflow.
Failures preserve source data and do not publish a success record.

## Scope, release and demonstration

See [the reproducible workflow](provisional-research-assessments.md#bounded-native-volume-offline-workflow).
The native-volume synthetic run and replay produced identical profiles. Final
observed process-tree peak working set was 82,345,984 bytes, including the Windows
venv launcher and child. This is an observation, not a kernel hard-memory guarantee.
Implementation/environment hashes in the final native-volume records bind the exact
replay source; all earlier evidence is retained.

This increment completes a supported research path, not all clinical Milestone 3
outcomes. Real lesion supervision, validated stenosis localization/severity and
stenosis XAI remain unavailable. Browser large-mask integration and reliable automatic
branch extraction remain incomplete. No restricted dataset was accessed. ImageCAS
CC BY-NC 4.0 restrictions and separate ImageCAS-X attribution remain intact.

Both `clinical_gate_authorized` and `training_release_authorized` remain false.
M1/M2 results/checkpoints and the M4 reviewer workflow/migrations are preserved.
Only the explicitly authorized disposable QA container was restarted. No staging
migration, deployment, real backup/restore, commit, push or merge occurred.

## Files changed in this increment

New:

- `backend/app/services/tiled_candidate_profile.py`
- `backend/scripts/research_candidate_profile.py`
- `backend/scripts/demo_research_profile.py`
- `backend/tests/test_tiled_candidate_profile.py`
- `backend/tests/test_research_profile_cli.py`
- `frontend-react/src/components/ResearchEvidence.jsx`
- `frontend-react/src/lib/research-evidence.js`
- `frontend-react/tests/fixtures/research-procedure-boundaries.json`
- `docs/milestone3-research-completion.md`

Updated:

- `backend/app/services/experimental_candidates.py`
- `backend/tests/test_research_profile_evidence.py`
- `frontend-react/src/components/ResearchAssessment.jsx`
- `frontend-react/src/lib/research-assessment.js`
- `frontend-react/src/lib/exports.js`
- `frontend-react/tests/research-assessment.test.js`
- `frontend-react/tests/e2e/research-assessment.spec.js`
- `docs/provisional-research-assessments.md`
- The four root milestone/evidence/readiness reports.

## Dataset compatibility review - 2026-11-25

| Source | Modality and labels | Access / reuse status | Fit for VascuAI stenosis work |
|---|---|---|---|
| ImageCAS / ImageCAS-X v2 | 3D coronary CTA and artery masks; no verified lesion-level stenosis labels in the project manifests reviewed | ImageCAS-X v2 license remains unconfirmed; do not ingest or redistribute it | Useful for artery segmentation, not supervised lesion detection/severity |
| ASOCA / Coronary Atlas collection | 40 CTCA cases (20 normal, 20 diseased), NRRD volumes, majority-vote vessel masks from three annotators, VTP centrelines, and patient-level disease reports; no lesion boundaries/locations per finding | UK Data Service lists data as closed access and requires registration plus data-owner permission; the record references its End User Licence | Closest modality/geometry, but not a lesion-level localization or severity dataset; no files were accessed |
| Zenodo 4638863, diseased-coronary CTA | Record describes 20 CCTA cases, expert lumen segmentations, centrelines, calcium scores, and per-patient stenosis levels | Files are restricted. Zenodo requires evidence of ethics approval or waiver. The record does not publish a dataset licence field; no request or access was attempted | Potential future source for permitted geometry research, but its visible metadata does not establish lesion-level boundaries or authorize use here |
| ARCADE, Zenodo 10390295 | 2D X-ray coronary angiography PNG/COCO annotations, including stenosis-region segmentation; distinct from 3D CTA | Zenodo record is open; its Rights/License field is blank in the record inspected, so redistribution terms remain unconfirmed | Annotation task is relevant, but modality, dimensionality and physical geometry are incompatible with the current 3D CT inference pipeline |

At that point, the current supported deliverable was bounded offline geometry-based research evidence from explicit source-bound masks/branches, with visual navigation, structured reporting, and database-derived analytics. No new clinical or patient-case predictor was added. Existing synthetic fixtures verified software mechanics only; no synthetic model had yet been trained and no clinical performance claim was made.

**Milestone 3 remains incomplete.** A qualified, authorized lesion-level dataset or expert review protocol is still needed for lesion detection/localization and severity validation. Clinical and training authorization flags remain false.

Sources: [UK Data Service ASOCA record](https://reshare.ukdataservice.ac.uk/855916/); [Zenodo 4638863 record](https://zenodo.org/records/4638863); [Zenodo ARCADE record](https://zenodo.org/records/10390295); [ASOCA data descriptor](https://pmc.ncbi.nlm.nih.gov/articles/PMC10006074/).

## Synthetic-only 3D CNN execution - 2026-11-25

The request to demonstrate a genuine model pipeline was addressed without using patient or restricted data. `backend/app/services/synthetic_stenosis_ml.py` generates scalar 24x24x24 noisy oblique tube phantoms with controlled narrowing parameters, multiple-lesion variants, reproducible seeds and content hashes. It creates a stratified split of unique sample IDs, trains a small 3D CNN with cross-entropy/Adam, selects by validation loss, computes confusion matrix and accuracy/precision/recall/F1 on an untouched synthetic test split, writes a checkpoint and summary, supports synthetic-provenance-only prediction, and returns a genuine 3D CNN Grad-CAM heatmap for reproducible generated samples. `backend/scripts/train_synthetic_stenosis.py` is the optional CLI. PyTorch is lazy-imported and not added to default application dependencies.

Executed run: PyTorch 2.15.0+cpu in a temporary isolated Python 3.14 venv; 500 phantoms; seed 1729; 300 train / 100 validation / 100 test; 50 epochs. Held-out synthetic-only metrics: accuracy 0.31, macro precision 0.3152, macro recall 0.31, macro F1 0.3076. This is weak, near-chance evidence and is reported as a pipeline demonstration, not classifier success on real data. Checkpoint is outside the repository at `F:\vascuai-artifacts\runs\milestone3-synthetic-cnn-20261125T1245-v5+0530\synthetic-stenosis-cnn3d.pt`, SHA-256 `a264d54a1fb4c370673ecaa7f8d3733982c0132b6e88e83dab1993cabb497937`.

A fixed smoke input labelled `moderate` by the synthetic generator was predicted `normal` by this checkpoint, further demonstrating that it is not a useful classifier yet.

Inference refuses an input unless its metadata and bytes exactly reproduce from the synthetic generator. The model is not callable by case ID, not registered as a stenosis provider, and not wired into persisted analytics, patient viewer or clinical reports. Synthetic class bins (0%, 15-28%, 35-48%, 55-68%, 75-88% generated diameter reduction) are generator ranges only, not clinical thresholds. Grad-CAM is only available for the synthetic phantom model. Existing geometry profile calculations remain a separate, source-bound research workflow. There is still no integrated real-case stenosis pipeline, real lesion supervision, model/dashboard endpoint, clinical severity estimate, clinical percentage result or stenosis XAI. Both authorization flags are false.

Focused verification: **214 passed** across the scientific offline research suite and optional synthetic-model tests. No API, frontend, Docker, database, migration, production or staging changes were made for this experiment. Milestone 3 remains partial and deployment remains blocked.

## Synthetic workbench integration - 2026-11-25

The model pipeline now has an isolated authenticated browser/API demonstration, separate from clinical cases. Frontend route: `/research/experimental-stenosis`. API routes: `GET /api/v1/experimental-stenosis/status`, `POST /api/v1/experimental-stenosis/samples`, and `POST /api/v1/experimental-stenosis/analyze`. Inputs are bounded IDs/class/seed values; the backend creates the fixed 24³ phantom itself. Analysis verifies a configured checkpoint's absolute file path, size, SHA-256 and synthetic-only metadata, then emits an explicitly experimental geometry profile, synthetic candidate locations, provisional generator-style categories, uncalibrated class scores and genuine 3D Grad-CAM. A local JSON summary can be downloaded. There is no database persistence/history and no patient-case input or association.

Frontend tests passed (658 unit tests; 4 focused browser tests), lint and production build passed with warnings recorded in `TEST_EVIDENCE.md`, and Python syntax compilation passed. Six direct isolated backend API/model tests passed using the pre-existing temporary PyTorch environment; the normal backend pytest setup could not collect because `reportlab` is missing at application import. Browser results use mocked API fixtures, while TestClient exercised the backend route and checkpoint inference separately without an application database.

The existing v5 checkpoint was separately loaded from its external artifact path after matching its recorded SHA-256 and completed a freshly generated phantom analysis with 3 provisional geometry candidates and a `[24,24,24]` Grad-CAM. The smoke classification was `normal`; this is weak synthetic-model evidence, not a claim that the phantom or prediction is medically meaningful.

The work is a software demonstration only. Existing trained model evidence is weak (0.31 accuracy on 100 synthetic held-out examples, with a moderate smoke input classified as normal), and the generator inputs are scalar phantoms, not CT. The geometric percentages and categories are synthetic voxel-space measurements; they are not clinical stenosis values. There are no authorized qualified lesion labels, no real-image predictor, no clinical severity/percentage, no clinical Grad-CAM, and no validated stenosis findings. Both `clinical_gate_authorized` and `training_release_authorized` remain false. Milestone 3 remains **partial** and release/deployment is not approved by these checks.

### Controlled synthetic detector and frozen-checkpoint evaluation — 25 Nov 2026

A targeted synthetic-only increment extended the phantom generator with declared axis orientation, bounded intensity noise, optional two-lesion cases, and opt-in geometric truth strictly for internal synthetic tests. Default/API samples do not expose that truth. The detector was changed from a single broad voxel-count trigger to a radial-squared 90th-percentile area profile along the generator-provided axis, with peak prominence/separation to split multiple controlled lesions. The method declares its axis source as generator-provided; it is not an anatomical centerline extractor and must not be applied to CT or patient cases.

The controlled matrix covers 180 cases: 5 phantom classes x 6 axis orientations x 3 noise levels x 2 replicates, including 36 normal controls and 216 generated lesion instances. With a predeclared match tolerance of 2.8 axial voxels, observed candidate precision was 1.000 (207/207), recall 0.9583 (207/216), mean/median absolute localization error 0.3574/0.3551 axial voxels, multiple-lesion recall 0.9375, and false candidates on normal controls 0/36. The nine unmatched lesions reflect detector abstentions, not fabricated detections. This is software verification on the same known generator family, not independent scientific or clinical validation. Evidence: `F:\vascuai-artifacts\diagnostics\m3-test-evidence-20261125\candidate-benchmark.json` and `backend/tests/test_synthetic_candidate_benchmark.py`.

A second evaluation used 500 new generated phantoms (balanced 100 per class) with fixed seed `2026112600`, sample IDs `100000..100499`, and disjoint 300/100/100 train/validation/test reservations (20/class/split). The frozen checkpoint was evaluated, not retrained. Identity manifest hash: `59625c84d281b90bb644e62ed3ba12e2341d8e24346a89f1df57aa5370d6e8fb`; test hashes had zero overlap with reconstructed checkpoint training inputs. Artifacts: `F:\vascuai-artifacts\runs\milestone3-synthetic-eval-20261125T191500Z-v2`.

On the new 100-case synthetic test split, the frozen 3D CNN achieved accuracy 0.30, macro precision 0.2951, macro recall 0.30, and macro-F1 0.2887. Per-class F1: normal 0.4348, mild 0.4286, moderate 0.1429, severe 0.1739, critical/very severe 0.2632. The simple geometry baseline scored accuracy 0.96 and macro-F1 0.9594, but it has generator-specified geometry/axis access and is therefore an oracle-like synthetic comparator, not a deployment-equivalent baseline. Its performance only demonstrates that the controlled label generator is recoverable from its own parameters. Neither set of metrics estimates clinical performance. The checkpoint remains unchanged (SHA-256 `a264d54a1fb4c370673ecaa7f8d3733982c0132b6e88e83dab1993cabb497937`).

Fresh tests on 25 Nov: backend 1006 passed / 197 PostgreSQL-only skipped / 3 warnings; frontend unit 658 passed; full browser 221 passed / 3 opt-in real-volume tests skipped; actual-API browser 1 passed with the pinned synthetic checkpoint and 1 passed without checkpoint configuration. Production build and lint exit 0 (lint has 3 warnings; build reports large imaging-runtime chunks). Detailed commands/log paths are in `TEST_EVIDENCE.md`.

The new route `/api/v1/experimental-stenosis` and UI `/research/experimental-stenosis` remain authenticated, synthetic-only, non-persistent, and separate from patient-case APIs. Live tests confirmed role denial, invalid payload rejection, disabled model action when checkpoint is absent, Grad-CAM/JSON export when configured, and false clinical/training authorization flags. These checks used temporary SQLite only and did not touch staging.

**Status remains PARTIAL/BLOCKED for clinical Milestone 3:** suitable qualified lesion-level supervision and independent clinical review are unavailable. There is no real CT stenosis predictor, clinical severity or percentage estimate, calibrated confidence, clinical XAI, or validated result. Do not register a clinical provider or authorize training release. `clinical_gate_authorized=false`; `training_release_authorized=false`.
# Synthetic geometry measurement validation — 25 November 2026

This increment adds a reproducible, controlled phantom benchmark for the existing
synthetic stenosis measurement path. It does not add patient inference, clinical
stenosis capability, or clinical ground truth.

## Method and safeguards

The benchmark generates normal, single-lesion and multi-lesion phantom profiles
with six axis/orientation configurations, three noise levels and two replicates
(180 cases, 216 lesions). Ground-truth radii, percent narrowing and lesion centers
are stored separately in the benchmark fixture records. Before calling the estimator,
the benchmark constructs a reduced input containing only source identity, hash,
axis and synthetic image/profile data; truth values and class labels are excluded.
Candidate matches use a one-to-one nearest match with a documented 2.8 axial-voxel
tolerance. Severity categories use configurable provisional synthetic thresholds
of 10, 30, 50 and 70 percent.

## Results

Candidate precision was 1.0000 and recall 0.9583 (207/216); multi-lesion recall
was 0.9375 (135/144 lesions recovered in multi-lesion cases), and normal false
candidates were 0/36. Across profiles: reference-radius MAE/RMSE/bias 0.3098 /
0.3265 / -0.3098 synthetic voxels; minimum-radius 0.2278 / 0.2853 / -0.2245
synthetic voxels; narrowing 2.2917 / 3.5759 / +0.9953 percentage points. Matched
lesion localization MAE/RMSE/signed bias was 0.3574 / 0.4331 / +0.0139 axial voxels.
Matched lesion narrowing MAE/RMSE/bias was 1.8785 / 2.7432 / -0.1213 percentage
points. Maximum absolute narrowing error was 13.0818 points. Matched provisional
severity accuracy/macro-F1 was 0.9855 / 0.9872 against generator-derived categories.

The UI reports the estimates, availability, method parameters and provenance.
Measurement confidence and uncertainty are null and displayed as unavailable;
no confidence score is fabricated. Research JSON binds the results to source hash,
method/version and threshold parameters. Category names are explicitly provisional
and are not clinical severity classifications.

## Limits and reproducibility

Radiographic voxels in this benchmark are synthetic unit-grid values, not calibrated
physical millimeters. The generator's analytic geometry is not independent human
annotation. High category agreement is partly a consequence of applying the same
provisional threshold definitions to generator-defined synthetic narrowing; it must
not be represented as classifier performance. Results do not validate image-based
stenosis detection or generalization to real scans. Maximum error is material and
must be shown alongside means.

Artifact: `F:\vascuai-artifacts\runs\m3-synthetic-geometry-measurement-20261125T091300Z\measurement-benchmark.json`.
The CLI and logs are under `F:\vascuai-artifacts\diagnostics\m3-measurement-validation-20261125\`.
The frozen CNN checkpoint remains unchanged (SHA-256
`a264d54a1fb4c370673ecaa7f8d3733982c0132b6e88e83dab1993cabb497937`); its separate
500-case disjoint synthetic test reported macro-F1 0.2887. CNN and geometry scores
are reported separately; the geometry baseline has generator-parameter access and
is not a fair model comparator. Neither is clinical evidence.
Both clinical and training authorization flags remain false.

---

## 25 Nov 2026 — separate real-volume research QC increment

An authenticated, non-persistent endpoint was added at `POST /api/v1/experimental-stenosis/real-volume/analyze`. It accepts only a 3D `.nii`/`.nii.gz` CT and a matching binary 0/1 segmentation mask; both are size-bounded and validated for complete NIfTI payload, finite voxel values, equal dimensions, valid affines, affine alignment and compatible declared units. Temporary upload files are deleted after processing. The response records CT and mask-file SHA-256, native shape/orientation/spacing, RAS-mm spacing and a CT-bound geometry fingerprint when CT units support conversion.

The response reports foreground voxel/component counts and, only for physical geometry and masks no larger than 4 million voxels, attempts the existing conservative experimental branch-graph extractor. The graph may abstain on topology, thinning or support checks; it is a digital skeleton diagnostic, not a validated anatomical centerline. The general input cap is 67,108,864 spatial voxels; automatic graph extraction has the stricter 4,000,000-voxel cap.

Crucially, uploaded mask semantics are not source-attested. The ImageCAS audit identifies coronary artery segmentation masks, not lumen or lesion labels, and records unresolved mask units. Therefore the API returns no lesion candidates, no cross-sectional lumen profile, null reference/minimum lumen measurements, null percentage narrowing and null provisional severity. It never calls the synthetic CNN or Grad-CAM, persists no case/result, and enforces `clinical_validation=false`, `clinical_gate_authorized=false`, `training_release_authorized=false`. This completes a bounded real-volume input/QC and topology demonstration only; stenosis detection and measurement remain unavailable until a suitable source and its lumen semantics are independently verified.

Fresh checks: backend focused tests **17 passed, 1 skipped** (optional synthetic Torch-runtime test); frontend unit suite **664 passed**; focused browser workflow **5 passed**; Python compile, frontend production build, lint and staged/unstaged `git diff --check` exited 0. Lint reported three existing warnings (AuthContext and synthetic page); build reported the existing large NIfTI/runtime chunks. Browser testing used mocked API responses; API tests used temporary NIfTI fixtures and role dependency overrides, not a live database. No original dataset file, patient data, staging, database, model checkpoint, or Docker resource was accessed. The 164 staged paths, branch and HEAD were preserved; no files were staged or committed.

Final verification addendum (25 Nov 2026): after adding authorization-change invalidation coverage, the focused browser suite completed **6/6 passed**. The full application OpenAPI was generated under temporary test-only settings with warnings treated as errors and included `POST /api/v1/experimental-stenosis/real-volume/analyze` with unique operation ID `analyze_real_volume_research_upload`. The backend focused result remains **17 passed, 1 skipped**; the skip is the optional synthetic PyTorch runtime check. No patient, staging or production database was connected.
