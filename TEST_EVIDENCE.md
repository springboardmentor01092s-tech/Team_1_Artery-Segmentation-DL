# Test evidence

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
