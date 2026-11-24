# Milestone 3 research completion increment

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
