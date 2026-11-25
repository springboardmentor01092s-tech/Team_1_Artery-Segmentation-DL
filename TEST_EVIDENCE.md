# Test evidence

## Synthetic geometry measurement increment — 25 November 2026

- Benchmark command: `python scripts\benchmark_synthetic_geometry.py --output-dir F:\vascuai-artifacts\runs\m3-synthetic-geometry-measurement-20261125T093700Z` (exit 0); repeat at `T094000Z` matched byte-for-byte. SHA-256 for both result files: `BBC6BC6C4E1FDB74032B85BF1C574BDBDC800F1D09A2CE3FED7810C92274F331`. Main JSON: `F:\vascuai-artifacts\runs\m3-synthetic-geometry-measurement-20261125T093700Z\measurement-benchmark.json`; CLI logs: `geometry-benchmark-final-audit.log` and `geometry-benchmark-repeat.log` under the diagnostics folder.
- Measurement sample: 180 profiles / 216 lesion truth records; estimator input excluded independent truth fields. Detection: precision 1.0000, recall 0.9583, multi-lesion recall 0.9375, normal false candidates 0/36.
- Frozen CNN remains a separate preserved artifact (SHA-256 `a264d54a1fb4c370673ecaa7f8d3733982c0132b6e88e83dab1993cabb497937`); prior disjoint 500-phantom synthetic test reported macro-F1 0.2887. It is not merged with or treated as validation of this geometry measurement procedure.
- Profile-level metric summaries (synthetic voxels unless stated): reference radius n=180 MAE 0.3098, RMSE 0.3265, bias -0.3098; minimum radius n=180 MAE 0.2278, RMSE 0.2853, bias -0.2245; narrowing n=180 MAE 2.2917 pp, RMSE 3.5759 pp, bias +0.9953 pp. Matched lesion localization n=207 MAE 0.3574, RMSE 0.4331 axial voxels, signed bias +0.0139 axial voxels; matched lesion narrowing MAE 1.8785 pp, RMSE 2.7432 pp, bias -0.1213 pp. Maximum absolute narrowing error 13.0818 pp.
- Absolute-error p50 / p90 / maximum: reference radius 0.2996 / 0.4089 / 0.8253 synthetic voxels; minimum radius 0.1798 / 0.4888 / 0.7448 synthetic voxels; profile narrowing 1.4844 / 5.0143 / 13.0818 pp; matched localization 0.3551 / 0.6391 / 1.2844 axial voxels.
- Provisional synthetic-only severity: thresholds [10, 30, 50, 70]%; matched candidate accuracy 0.9855, macro-F1 0.9872. Full profile accuracy 0.9833, macro-F1 0.9833. These are deterministic categories derived from the same synthetic measurement procedure, not clinical label performance.
- Backend M3-focused regression: **18 passed, 2 skipped**, exit 0. The skips are PyTorch-dependent model/Grad-CAM tests because this Python runtime has no Torch. Full backend rerun: **997 passed, 198 skipped, 2 warnings**, exit 0, 186.57 seconds. Skips include PostgreSQL-only concurrency tests unavailable in this run and optional Torch/runtime tests; they are not passes. Temporary pinned test dependencies were installed outside the repo; no requirement file changed.
- Frontend `npm test`: **662 passed, 0 failed**. Lint: exit 0 with three warnings (experimental page state/ref-effect warnings and existing AuthContext Fast Refresh warning). Production build: exit 0 with the existing large imaging-bundle warning. Logs: `F:\vascuai-artifacts\diagnostics\m3-measurement-validation-20261125\frontend-unit-audit.log`, `frontend-lint-audit.log`, `frontend-build-audit.log`.
- Experimental research browser spec: **4 passed**. Full browser suite after the response-contract correction: **221 passed, 4 skipped, 0 failed**. Skips: two PostgreSQL-backed stenosis acceptance tests require the disposable acceptance harness; the experimental live-API test requires explicit disposable API credentials; and the real-volume viewer test requires explicit de-identified CT/mask/metadata paths. The earlier narrow-viewport label timeout was not reproduced in the focused evaluation spec (12/12) or the full suite. An intermediate test-harness missing-import failure was fixed, then the export assertion and full suite passed. Logs are under `F:\vascuai-artifacts\diagnostics\m3-measurement-validation-20261125\`.
- Final audit boundary: the benchmark was run twice with byte-identical output (SHA-256 above). Clinical/training authorization remain false. This audit did not use patient data, staging, a database, or deployed services; PostgreSQL-specific behavior and PyTorch/Grad-CAM runtime behavior remain unverified by this run.
- Clinical and training authorization flags remain false. No clinical or patient-data test was performed.

---

## Fresh continuation checks — 24 November 2026

- Focused PostgreSQL amendment, migration and adjudication suite: **37 passed**,
  exit 0, one existing Starlette/httpx deprecation warning. Log:
  external diagnostics `project-continuation-20261124/review-amendment-postgres.log`
  (not stored in Git).
- Frontend unit suite: **650 passed**, exit 0. Lint: exit 0 with the existing
  AuthContext Fast Refresh warning. Production build: exit 0 with the existing
  large-chunk warning. Logs are in the same diagnostics directory.
- Broad available PostgreSQL suite: **881 passed, 13 skipped, 3 warnings**, exit 0.
  It ran against a unique QA schema on the isolated closeout QA container. Log:
  `project-continuation-20261124/backend-available-fixed-verbose.log` (external).
- The first corrected-source run exposed one stale assertion in
  `test_populated_migration_chain_and_rollback_preservation`; its migration list
  stopped at 0015. The expected chain was extended to 0016 without changing the
  rollback/data-preservation assertions. The targeted test passed, then the full
  available suite passed. Earlier collection errors were due to missing SciPy.
- Nine SciPy-dependent research modules remain excluded from this API venv; the
  offline-research API test also skips without SciPy. Three Torch/MONAI runtime
  tests skip without Torch, and two Windows symlink checks plus live/restore opt-ins
  skip by design/host capability. The scientific suite was not freshly rerun.
- Prior full-suite and synthetic-restore results remain historical evidence. Their
  cited external run folder was not present on this machine during this continuation,
  so those logs could not be freshly reopened here.

The fresh PostgreSQL tests used the separately labelled closeout QA container and a
unique `vascuai_test_*` schema, not staging. They establish software behavior only,
not clinical validity or reviewer qualification.

## Final engineering ? fresh actual results

Updated 24 November 2026. Evidence: `final-engineering-20261124T093721Z`.
Branch `codex/milestone3-review`; HEAD remains `e37b7c87eebe5099686687eacd6a6db897d2e6c7`.
At report time, changes were local and unstaged. The later preflight staged all 164 pending paths locally; no commit, push, merge, staging migration or deployment has occurred.

External logs are under `final-engineering-20261124T093721Z`. Runs overlap; do not sum.
All test writes use disposable PostgreSQL/random schemas or in-memory SQLite.

| Check | Final actual result | Log |
|---|---|---|
| Frontend `npm test` | 649 passed; exit 0 | frontend-unit-final.log |
| Build / lint | exit 0 / 0; existing chunk/Fast Refresh warnings | build-final.log / lint-final.log |
| Full available PostgreSQL | 874 passed, 13 skipped, 3 warnings; exit 0 | full-postgresql-final.log |
| Isolated scientific regressions | 211 passed; exit 0 | research-acceptance-final.log |
| Complete browser | 216 passed, 3 skipped; exit 0 | browser-full-final.log |
| Final CT display subset | 18 passed; exit 0 | browser-display-final.log |
| New offline API | 25 passed; exit 0 | offline-api-final.log |
| Adjudication PG | 29 passed; exit 0 | adjudication-pg-final.log |
| Actual-API reviewers and small/native research | 3 passed; exit 0 | actual-api-final.log |
| SQLite auth/review/cleanup | 76 passed, 3 PG-only skips; exit 0 | sqlite-auth-review-final.log |
| Synthetic current-schema dump/restore | 1 passed; exit 0 | synthetic-restore.log |
| Model comparison | 100 predictions; all 53 artifacts identical to prior | M2-FINAL-VERIFICATION.json |

Available-PG exclusions: old frozen automatic matrix and scientific modules executed
separately. Skips: optional SciPy API modules rerun in research environment; absent
Torch/MONAI, Windows symlink privileges, live/restore opt-ins, and SQLite-only assertion.
Actual-API and synthetic restore opt-ins were executed separately. Browser skips are
two provider-dependent stenosis tests and one supplied real-volume opt-in. No opt-in
safeguard or failing assertion was removed. Existing deprecation/sourcemap warnings
remain. No new model inference, real patient test, training or clinical validation.

Commands: existing pinned private `qa/run_disposable_tests.py` with test arguments
recorded in its test-runs.jsonl; complete browser `npx playwright test --workers=1` on
isolated loopback Vite; research `python -B -m pytest --noconftest -q` for vessel,
experimental candidates, profile/storage/CLI, characterization and new automatic
plan/CLI modules; SQLite targeted auth/access/adjudication/isolation tests. No actual
application environment credentials were exposed or used by test suites.

Failures investigated and corrected, with original logs preserved: test-only flipped
coordinate expectation (now independent world-coordinate assertion); curved reference
tip definition; Pydantic fixture model_copy bypass; separate native/small artifact
folders; SQLite DROP of populated self-referencing history. SQLite cleanup is limited
to in-memory tests, restores foreign keys before test bodies, and rejects file DBs
before connecting. Existing assertions and runtime constraints remain in force.
A broad browser attempt used an old collected test after a source edit; the fresh
frozen-source full run passed 216/3. No failed attempt is called a successful run.

Fresh release inspection is read-only: schema 0010; old images; health 200; unauthorized
reads 401; new reviewer route 404. Retained backup hashes/archive/ACL and listing pass;
backup schema 0009 is stale. The new synthetic restore is not a current staging
DB/private-storage backup or operational recovery test.

---

## Prior entries (preserved)

## Fresh verification ? offline browser / centerline characterization, 24 November 2026

External run: `m3-browser-centerlines-20261124T082756Z`.
All PostgreSQL writes are to the pinned disposable QA database with a new test schema;
no application/staging DB is accessed by tests. Counts overlap; never add them.

| Check | Actual result | Run log |
|---|---|---|
| `npm test` | 636 passed; 0 failed/skipped; exit 0 | frontend-unit.log |
| `npm run build` | exit 0; existing chunk-size warning | build.log |
| `npm run lint` | exit 0; existing AuthContext Fast Refresh warning | lint.log |
| Full available PostgreSQL | 868 passed, 12 skipped, 3 warnings; exit 0 | full-postgresql.log |
| Offline verification PostgreSQL | 22 passed; exit 0 | offline-api-final.log |
| Actual-API offline browser | 1 passed; exit 0 | offline-live-retry.log |
| Isolated scientific regressions | 178 passed; exit 0 | research-regressions.log |
| Complete browser | 213 passed, 3 skipped; exit 0 | browser-full.log |
| New transport/UI tests | 2 passed; exit 0 | offline-browser-retry.log |
| New small topology probes | 8 passed; extraction admitted 1/8 | branch-probes.log / BRANCH-CHARACTERIZATION.csv |

Commands (existing private QA runner injects disposable DB credentials in memory):

```
python -B run_disposable_tests.py tests --ignore=tests/test_automatic_branches.py --ignore=tests/test_branch_characterization.py --ignore=tests/test_experimental_candidates.py --ignore=tests/test_vessel_analysis.py --ignore=tests/test_research_profile_evidence.py --ignore=tests/test_tiled_candidate_profile.py --ignore=tests/test_research_profile_cli.py -o faulthandler_timeout=60
python -B run_disposable_tests.py tests/test_offline_research_api.py
VASCULAI_OFFLINE_LIVE=1 python -B run_disposable_tests.py tests/test_offline_research_live.py
python -B -m pytest --noconftest -q backend/tests/test_experimental_candidates.py backend/tests/test_vessel_analysis.py backend/tests/test_research_profile_evidence.py backend/tests/test_tiled_candidate_profile.py backend/tests/test_research_profile_cli.py backend/tests/test_branch_characterization.py
npx playwright test --workers=1
```

The scientific command uses the existing research environment and PYTHONPATH=backend;
ordinary API tests use the existing backend environment. The full PG run skips two
modules requiring SciPy (new API tests rerun separately), optional Torch/model tests,
Windows symlink privileges and explicit live/restore checks. The actual offline API
browser opt-in was executed separately. Existing reviewer live/restore evidence is
retained from the previous increment; it was not freshly rerun in this increment.
Three browser skips remain two configured-provider stenosis tests plus an explicitly
supplied real-volume viewer test. No opt-in safeguard was removed.

Failure attempts retained externally: synthetic fixed-UUID directory collision;
public-export test initially used fields discarded by the allowlist (corrected to
actual result/notes fields); test locator used visible text instead of accessible
name; newly isolated reviewer fixture lacked explicit setup/assignment creation.
Corrected tests retain denial/assertion requirements. Final 22 API tests include
both assigned readers receiving 403 on the new route. No production guard weakened.

The actual-API rehearsal uses real HTTP/FastAPI/PostgreSQL and synthetic stored CT /
mask data. It verifies source recomputation, source navigation, R1/R2/R3, export,
reverified restore, and no mask/probability request. It is not real model inference,
expert annotation or clinical validation. Historical native-volume metrics are
clearly labelled; no frozen matrix/instrumentation or real dataset was run here.

Documentation QA: embedded fonts/icons/screenshots, internal links, no external
requests, desktop/mobile overflow checks, searchable A4 PDF and rendered-page review.
PDF tooling is isolated outside the application; app dependencies/lockfile unchanged.

---

## Historical entries (preserved)

Updated 24 November 2026 11:14 IST. Local increment `m3-completion-20261124T051538Z`; branch/HEAD unchanged. No commit, push, merge, staging migration or deployment.

## Fresh completion-increment verification

Evidence run: external `m3-completion-20261124T051538Z`. Counts overlap.

| Scope | Actual result | Log |
|---|---|---|
| Full frontend unit suite | 622 passed, exit 0 | frontend-final.log |
| Public research helpers (included above) | 50 passed | research-unit-final.log |
| Full browser suite | 211 passed, 3 skipped, exit 0 | browser-full.log |
| Latest research/reporting browser checks | 19 passed, exit 0 | browser-security-final.log |
| Full available disposable PostgreSQL | 868 passed, 10 skipped, exit 0 | postgres-full.log |
| Actual-API reviewer browser rehearsal | 1 passed, exit 0 | review-live.log |
| Offline research/backend/schema/CLI | 119 passed, exit 0 | research-verified.log |
| Build / lint | exit 0 / exit 0 | build.log / lint.log |
| Native-grid synthetic run/replay | identical profile hashes, 4,276,737 voxels | NATIVE-FINAL-VERIFICATION.json |
| Diff / preservation | final checks recorded externally | PRESERVATION-FINAL.json |

The same pinned QA container/image/volume was started explicitly for these tests.
Only disposable schemas/databases were written; no staging/native application DB
was targeted. The 10 backend skips cover missing optional Torch/MONAI, Windows
symlink privilege and explicit live/restore opt-ins; actual reviewer live testing
ran separately. The browser skips are two provider-dependent stenosis tests and
the explicit real-volume opt-in. No safeguards were weakened.

Synthetic-only SciPy commands and the actual PostgreSQL command/reproduction
exclusions are recorded in `docs/milestone3-research-completion.md`. The new offline
modules are not imported into FastAPI and require the existing SciPy research env.
No models, real lesions, Testing or Validation training were used.

The new axe check initially failed on invalid ARIA labels on SVG polylines; valid
SVG titles fixed it. Invalid source/units, rounded native geometry, storage/frontier
limits, gzip expansion, collisions, source races, parameter types/over/underflow,
standalone tampering and metric/report isolation all have regression coverage.
Previous code/harness failures remain in their original logs and are explained in
the implementation report. Latest applicable runs pass.

Native-release replay measured 82,345,984 bytes maximum observed process-tree working
set across two successful runs (Windows launcher plus child); elapsed about 1.32 and
1.3 seconds. This is observation, not a kernel hard-memory guarantee. Buffer,
frontier and file-size bounds are enforced in code. Maximum-size production-volume
performance and clinical accuracy are not established by this synthetic example.


---

## Prior sprint evidence (historical, preserved)

Updated 24 November 2026 10:15 IST. Evidence: external run `ai-assisted-m3-20261124T042751Z`. Branch and HEAD unchanged. All new work remains local, unstaged and undeployed.

## Fresh provisional-research checks

Evidence directory: external `ai-assisted-m3-20261124T042751Z`. Counts overlap.

| Command / scope | Actual result | Log |
|---|---|---|
| `npm test` | 607 passed, 0 skipped, exit 0 | frontend-final-source.log |
| New public research helper tests (included above) | 35 passed | research-unit-final.log; final full suite |
| Playwright research + existing preview + blinded CT + assignments/adjudication, workers=1 | 25 passed, exit 0 | browser-final-source.log |
| `pytest --noconftest -q --tb=short tests/test_research_profile_evidence.py tests/test_experimental_candidates.py` | 39 passed, exit 0 | profile-backend-final.log |
| `pytest --noconftest -q --tb=short tests/test_quantitative_gate.py`, isolated test configuration | 29 passed, exit 0 | quantitative-gate-isolated.log |
| `npm run build` | exit 0; existing large-chunk warning | build-final-source.log |
| `npm run lint` | exit 0; existing AuthContext Fast Refresh warning | lint-release.log |
| `git diff --check` | exit 0 | diff-check.log |

Browser tests use the actual React/NiiVue components with synthetic CT and
intercepted APIs. They do not establish fresh actual-API/PostgreSQL or real-volume
clinical performance. New browser tests exercise research download/restore, altered
record refusal, caliper arithmetic, actual candidate crosshair navigation, print
hiding, delayed file/session changes and delayed hashing/session changes. No API
writes occurred. Python independently regenerates the asymmetric fixture with the
existing frozen candidate operator, and validates refusal of simulated records by
otherwise valid human-review schemas. Quantitative gates remain empty.

Two repeated calculations produce identical packets. Synthetic focal: R1=1, R2=1;
asymmetric: R1=1, R2=0, 5 unresolved section disagreements. See external
RESEARCH-SYNTHETIC-RESULTS-FINAL.json and both source-bound JSON examples. These are not
sensitivity/specificity, model confidence, expert labels or actual model inferences.

### Failed attempts retained and corrected or blocked

- An initial new export test passed a non-array to the public records helper. It
  was corrected to exercise a real records array with nested notes; no assertion
  or production guard was weakened.
- Initial browser run passed but exposed duplicate sibling keys after adding a
  source-reset key. A distinct research prefix fixed this; latest console-error
  assertions pass. Form controls were styled with existing classes after screenshot review.
- Pure quantitative tests initially lacked mandatory settings (22 passed, 7 import
  failures). Rerun with TESTING=true, new in-memory SQLite, generated ephemeral
  secret and external scratch paths passed all 29. No real DB was configured.
- The pinned PostgreSQL runner refused before test execution because the existing
  QA container is exited (same expected container/image identity). No container
  was started or replaced; no PostgreSQL result is claimed for this stage.

Complete backend/PostgreSQL and 208-browser evidence below belongs to the prior
completed sprint, not this stage. No migration, restore, model training or inference
was rerun here. Original failure logs and previous reports remain outside Git.


---

## Previous completed sprint evidence (retained; not a fresh rerun)

Updated 24 November 2026 09:41 IST. Branch `codex/milestone3-review`; base HEAD `e37b7c87eebe5099686687eacd6a6db897d2e6c7`. New code is uncommitted and undeployed. External evidence run: `completion-sprint-20261123T171203Z`.

All test writes target disposable QA PostgreSQL/SQLite, not application databases.
Runs overlap; do not sum their counts as unique coverage.

| Check | Actual result | External evidence |
|---|---|---|
| Frontend npm test | 572 passed, exit 0 | qa/frontend-manual-fallback.log |
| Production build | exit 0; existing chunk warning | qa/build-manual-final.log |
| Lint | exit 0; existing AuthContext Fast Refresh warning | qa/lint-manual-final.log |
| Full available PostgreSQL | 868 passed, 10 skipped, exit 0 | qa/regressions-b60bc5.log |
| Focused reviewer/concurrency/migration/restore | 27 passed, exit 0 | qa/regressions-5b1d46.log |
| Latest actual-API manual entry/R1/R2/third-reader | 1 passed, exit 0 | qa/regressions-0f15a2.log and actual-browser artifacts |
| Complete browser suite | 208 passed, 3 skipped, exit 0 | qa/browser-final-20261124.log |
| Viewer/resource fallback/integrity checks | 11 passed | qa/ct-fallback-final.log |
| Viewer/adjudication focused browser | 16 passed | qa/ct-fallback-after.log |
| CPU Torch inference/API | 74 passed, 2 platform skips | qa/torch-regressions.log |
| Vessel/candidate | 84 passed | qa/research-regressions.log |
| Comparison verifier self-tests | 8 passed | COMPARISON-VERIFIER-SELFTEST-20261124.json |
| Real saved-mask comparison | 100 files verified, no mismatch | FINAL-COMPARISON-INTEGRITY.json |
| Reproducibility repeat | 53 artifact hashes identical | COMPARISON-REPRODUCIBILITY.json |

Backend command arguments: qa/test-runs.jsonl. Full available PG command:

```
python -B -m pytest -q --tb=short --ignore=tests/test_automatic_branches.py --ignore=tests/test_experimental_candidates.py --ignore=tests/test_vessel_analysis.py -o faulthandler_timeout=60
```

These research modules need SciPy/scikit-image absent from that backend environment;
vessel/candidate tests ran separately. The automatic-branch matrix/instrumentation
was not rerun. PG skips: missing Torch/MONAI, two unsupported Windows symlink
operations and explicit live/restore opt-ins. Reviewer live and synthetic restore
were run separately; CPU Torch tests used the existing model environment. Local
MONAI runtime-specific tests remain unverified; saved validation does not establish
newly deployed SegResNet serving readiness.

Browser skips: two provider-dependent stenosis-live.spec.js tests and the explicit
supplied-volume viewer-real-volume.spec.js test. Safeguards were retained. Actual-API
reviewer tests use real HTTP/FastAPI/PostgreSQL with synthetic CT/accounts/credential
evidence; they are not real expert review or clinical validation.

## Failures corrected, evidence retained

- New session test expected logout 200 incorrectly. Existing contract is 204; test
  now checks 204/empty body and still checks revoked-token 401. Auth code unchanged.
- Large-CT probe failed because resource refusal hid the worksheet. Explicit native
  IJK/manual external-viewer preparation now works without raising caps; invalid
  points retain the old value, and integrity failures still block the worksheet.
- Earlier fixture matching/accessibility-label errors were corrected; local input
  errors do not masquerade as server revision conflicts. Assertions were retained.
- Synthetic restore strict DDL comparison exposed equivalent PostgreSQL VARCHAR-array/
  TEXT-array cast forms. Raw DDL retained; five named literal checks narrowly
  normalized. Table hashes/counts, indexes, other constraints, triggers/functions,
  sequences match. This is not a fresh staging backup.
- Initial comparison RAM logger observed the Windows venv launcher only. That root
  value is not claimed as total RAM. Corrected root+descendant observation repeated
  saved-mask verification, producing identical reports.

Corrected verification peak observed process-tree working set:
751017984 bytes; elapsed 270.52 seconds. This
is periodic observation, not a kernel hard limit. Baseline continuation kept CPU-only
4-thread operation, 1200 seconds/case, 4 GiB observed process-tree stop and 2 GiB output
cap; its total bound was 8400 seconds. Interrupted attempts remain in prior evidence.

## Backup/preservation

Fresh read-only staging: health/readiness 200, schema 0010, no new review routes.
Six old backup hashes/listing and 22 safe tar entries/13 file payloads verified;
nine ACL paths permit only the approved accounts. Historical full restore is 0009,
not current 0010. No real backup/restore/migration/deployment/restart occurred.
Current-schema synthetic restore used a new disposable DB retained for inspection.

External source checkpoint/final inventory records current hashes, Git state,
protected research/gate files and unchanged migrations 0010-0012. Historical 1,401-
entry reports are not substituted for a fresh baseline. Original 401/402/404 assets
and all 50 Val references were rehashed. Readable failure-log copies are sanitized;
original private evidence is retained. No credentials/tokens/medical contents appear
in these reports. Both authorization flags remain false in every review state.

## 2026-11-25 structured PDF follow-up (fresh)

- `python -B -m pytest -q tests/test_stenosis_reporting.py` against a newly created loopback-only disposable PostgreSQL 18 container: **26 passed**, one Starlette/httpx deprecation warning. Container removed after the test; its nine newly created, dangling anonymous test volumes were identified by creation time/anonymous-volume label, verified unused by all containers, and removed. Staging/demo containers and named volumes were preserved.
- `npm test`: **651 passed**, 0 failed/skipped.
- `npm run test:e2e -- tests/e2e/reporting.spec.js`: **16 passed**; these browser tests use mocked API responses.
- `npm run build`: passed; Vite warned that several imaging-related chunks exceed 500 kB. `npm run lint`: exit 0 with the existing `AuthContext.jsx` fast-refresh warning.
- Generated synthetic PDFs were parsed and every rendered page inspected: zero-candidate report 1 page; two-candidate report 2 pages; failed/status-only report 1 page. Page numbering was present; no replacement characters or `Skip to content` text was found.
- Temporary test environment only: `pip check` passed. No patient data, production/local application DB or staging DB was used.

## M3 focused research regression run - 2026-11-25

Command from `backend/`: `python -B -m pytest --noconftest -q --tb=short tests/test_tiled_candidate_profile.py tests/test_research_profile_cli.py tests/test_experimental_candidates.py tests/test_research_profile_evidence.py tests/test_automatic_branch_cli.py tests/test_automatic_branch_plan.py tests/test_branch_characterization.py tests/test_vessel_analysis.py` (disposable venv interpreter). Result: **211 passed**, exit 0, 26.33 s. These are synthetic/offline geometry, source-binding, branch/refusal, CLI and vessel-analysis regressions; they do not validate anatomy or clinical stenosis detection.

## 2026-11-25 synthetic 3D CNN experiment

- Optional runtime: isolated Python 3.14 venv, PyTorch `2.15.0+cpu`; project/default API environment was not changed.
- Combined offline research and optional model command from `backend/`: `python -B -m pytest --noconftest -q --tb=short tests/test_tiled_candidate_profile.py tests/test_research_profile_cli.py tests/test_experimental_candidates.py tests/test_research_profile_evidence.py tests/test_automatic_branch_cli.py tests/test_automatic_branch_plan.py tests/test_branch_characterization.py tests/test_vessel_analysis.py tests/test_synthetic_stenosis_ml.py` with the isolated torch site-packages on `PYTHONPATH`: **214 passed**, exit 0, 26.32 s.
- Training command: `python -B scripts/train_synthetic_stenosis.py --output <new-external-run-directory> --samples 500 --epochs 50 --seed 1729`. It trained a synthetic-only 3D CNN; split counts were train 300 / validation 100 / test 100 with disjoint sample IDs. Checkpoint reload, synthetic-provenance inference, modified-input refusal, and 24x24x24 3D Grad-CAM smoke test passed.
- Held-out synthetic test metrics only: accuracy 0.31; macro precision 0.315238; macro recall 0.31; macro F1 0.307646; n=100. This is weak and does not establish clinical or real-image performance.
- A reproducible `moderate` synthetic phantom smoke case was misclassified as `normal`; the trained checkpoint is not considered a useful classifier.
- Checkpoint: `F:\vascuai-artifacts\runs\milestone3-synthetic-cnn-20261125T1245-v5+0530\synthetic-stenosis-cnn3d.pt`; SHA-256 `a264d54a1fb4c370673ecaa7f8d3733982c0132b6e88e83dab1993cabb497937`. Run metadata, split IDs, dataset hash, training history, confusion matrix, and false authorization flags are in the adjacent `training-summary.json`.
- No API/browser/Docker integration or medical-data tests were run for this synthetic-only model; none was added. No clinical or training release authorization was enabled.

## 2026-11-25 synthetic stenosis workbench integration

- `frontend-react`: `npm test` — **658 passed, 0 failed, 0 skipped**.
- `frontend-react`: `npm run test:e2e -- tests/e2e/experimental-stenosis.spec.js` — **4 passed**. This browser suite mocks the API; it verifies synthetic generation/result rendering/export, unavailable-checkpoint state, clinician denial, and stale in-flight result invalidation after changing parameters, not a live FastAPI/model call.
- `frontend-react`: `npm run lint` — exit **0**; warnings: existing `AuthContext.jsx` fast-refresh warning and two React hook/effect warnings in `ExperimentalStenosis.jsx`.
- `frontend-react`: `npm run build` — passed; Vite reports imaging-related chunks larger than 500 kB.
- `backend`: `python -m compileall -q app/schemas/experimental_stenosis.py app/routers/experimental_stenosis.py app/services/synthetic_stenosis_ml.py app/main.py app/core/config.py` — passed.
- `backend`: standard `python -m pytest -q tests/test_experimental_stenosis_api.py tests/test_synthetic_stenosis_ml.py` — **blocked at conftest import** (`ModuleNotFoundError: reportlab`). Focused isolated command `python -m pytest --noconftest -q tests/test_experimental_stenosis_api.py tests/test_synthetic_stenosis_ml.py`, with ephemeral test settings and the pre-existing temporary PyTorch 2.15.0+cpu site-packages on `PYTHONPATH`, — **6 passed**. This included TestClient route/auth/input/checkpoint tests and actual temporary synthetic checkpoint inference/Grad-CAM tests; no app DB was used and no dependencies were installed.
- The existing external v5 checkpoint was also freshly loaded by exact SHA-256 and used for a generated phantom smoke inference with the same isolated PyTorch package directory. Output: checkpoint digest matched; `synthetic_test_split_only` metadata accepted; analysis completed; 3 geometry candidates; Grad-CAM shape `[24,24,24]`; model predicted `normal`; both authorization flags remained false. This smoke prediction is not a clinical result and the model remains weak.
- `git diff --check` and `git diff --cached --check` — passed. Existing staged manifest remains 164 paths with recorded cached patch hash `9855865864da347d36f1de5ad854c29ba167dbaf`; no staging operation was performed.

## Fresh verification — 25 Nov 2026

All logs are outside the repository at `F:\vascuai-artifacts\diagnostics\m3-test-evidence-20261125\`.

| Area | Command / setup | Result |
|---|---|---|
| Backend | From `backend`: isolated Python 3.14 venv installed `requirements-dev.txt` (including existing `reportlab==5.1.0`); `python -B -m pytest -q --cov=app --cov-report=term`; SQLite-only `TESTING=true`, no `TEST_DATABASE_URL`; existing isolated PyTorch 2.15 CPU site-packages exposed by `PYTHONPATH` | **1006 passed, 197 skipped, 3 warnings, exit 0, 242.23 s.** PostgreSQL-only concurrency/integration cases skipped; not a PostgreSQL pass. |
| Frontend unit | `npm test` | **658 passed, 0 failed, exit 0.** |
| Frontend browser | `npm run test:e2e -- --reporter=line` | **221 passed, 3 skipped, exit 0, 3.4 min.** Three skips are explicit real-volume opt-in checks; no real dataset volume was supplied to this run. |
| Live API browser, checkpoint configured | `npm run test:e2e -- tests/e2e/experimental-stenosis-live.spec.js --reporter=line`; real local FastAPI on loopback, fresh SQLite database migrated to Alembic head, temporary Researcher/Clinician accounts, pinned external synthetic checkpoint | **1 passed, exit 0.** Browser called real status/sample/analyze APIs, checked Grad-CAM and downloaded JSON; Clinician denied (403), invalid/extra case payloads rejected (422), both auth flags false. |
| Live API browser, checkpoint absent | Same focused test with a separate local API process and no synthetic checkpoint environment variables | **1 passed, exit 0.** Status unavailable, sample remained usable, analysis action stayed disabled. |
| Frontend lint | `npm run lint` | **exit 0**, 3 warnings: existing AuthContext fast-refresh warning and two warnings in `ExperimentalStenosis.jsx` (synchronous effect reset; effect cleanup ref access). |
| Frontend production build | `npm run build` | **exit 0**; large chunk warning for NIfTI/wasm runtime assets. |
| Candidate matrix | `pytest -q tests/test_synthetic_candidate_benchmark.py tests/test_synthetic_stenosis_ml.py tests/test_experimental_stenosis_api.py` | **13 passed, 1 warning** (focused run); same tests also included in full backend run. Separate exact metric calculation saved as `candidate-benchmark.json`. |
| Frozen model evaluation | `backend/scripts/evaluate_synthetic_stenosis.py`, output `F:\vascuai-artifacts\runs\milestone3-synthetic-eval-20261125T191500Z-v2` | 500 balanced generated samples, disjoint 300/100/100 splits, checkpoint training hash overlap 0. Model synthetic test macro-F1 **0.2887**; geometry baseline **0.9594**; candidate precision **0.8774**, recall **0.9118**, mean localization error **0.3199 axial voxels**. |
| Static/diff checks | Python AST parse of touched backend files; `git diff --check`; `git diff --cached --check` | See final command result in this report update; no source formatting changes from the check. |

The first live-browser attempt used `.test` e-mail domains, which Pydantic EmailStr correctly rejected as reserved. The disposable QA account addresses were changed to `example.com`; no application code was changed for that setup issue. The first evaluation attempt is retained in separate `...-v1` with `RUN-STATUS.json` marking the provenance-validation failure; the successful run is `...-v2`. No artifacts were overwritten.

No PostgreSQL service, staging database, Docker service, patient data, Testing split, or patient-case inference was used. Full suite skipped 197 PostgreSQL-dependent checks, so their behavior is not newly certified here. Both clinical and training authorization flags are false.

## 25 Nov 2026 — separate real-volume research QC increment

An authenticated, non-persistent endpoint was added at `POST /api/v1/experimental-stenosis/real-volume/analyze`. It accepts only a 3D `.nii`/`.nii.gz` CT and a matching binary 0/1 segmentation mask; both are size-bounded and validated for complete NIfTI payload, finite voxel values, equal dimensions, valid affines, affine alignment and compatible declared units. Temporary upload files are deleted after processing. The response records CT and mask-file SHA-256, native shape/orientation/spacing, RAS-mm spacing and a CT-bound geometry fingerprint when CT units support conversion.

The response reports foreground voxel/component counts and, only for physical geometry and masks no larger than 4 million voxels, attempts the existing conservative experimental branch-graph extractor. The graph may abstain on topology, thinning or support checks; it is a digital skeleton diagnostic, not a validated anatomical centerline. The general input cap is 67,108,864 spatial voxels; automatic graph extraction has the stricter 4,000,000-voxel cap.

Crucially, uploaded mask semantics are not source-attested. The ImageCAS audit identifies coronary artery segmentation masks, not lumen or lesion labels, and records unresolved mask units. Therefore the API returns no lesion candidates, no cross-sectional lumen profile, null reference/minimum lumen measurements, null percentage narrowing and null provisional severity. It never calls the synthetic CNN or Grad-CAM, persists no case/result, and enforces `clinical_validation=false`, `clinical_gate_authorized=false`, `training_release_authorized=false`. This completes a bounded real-volume input/QC and topology demonstration only; stenosis detection and measurement remain unavailable until a suitable source and its lumen semantics are independently verified.

Fresh checks: backend focused tests **17 passed, 1 skipped** (optional synthetic Torch-runtime test); frontend unit suite **664 passed**; focused browser workflow **5 passed**; Python compile, frontend production build, lint and staged/unstaged `git diff --check` exited 0. Lint reported three existing warnings (AuthContext and synthetic page); build reported the existing large NIfTI/runtime chunks. Browser testing used mocked API responses; API tests used temporary NIfTI fixtures and role dependency overrides, not a live database. No original dataset file, patient data, staging, database, model checkpoint, or Docker resource was accessed. The 164 staged paths, branch and HEAD were preserved; no files were staged or committed.

Final verification addendum (25 Nov 2026): after adding authorization-change invalidation coverage, the focused browser suite completed **6/6 passed**. The full application OpenAPI was generated under temporary test-only settings with warnings treated as errors and included `POST /api/v1/experimental-stenosis/real-volume/analyze` with unique operation ID `analyze_real_volume_research_upload`. The backend focused result remains **17 passed, 1 skipped**; the skip is the optional synthetic PyTorch runtime check. No patient, staging or production database was connected.
