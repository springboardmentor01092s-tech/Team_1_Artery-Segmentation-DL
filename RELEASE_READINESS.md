# Release readiness

## M3 synthetic geometry validation update — 25 November 2026

**Not ready for clinical release or staging deployment.** A controlled synthetic
measurement benchmark and experimental UI/export increment are available for
research demonstration only. The benchmark covers 180 generated cases and 216
lesions; its maximum absolute narrowing error was 13.08 percentage points. It does
not establish accuracy on CT anatomy, clinical calibration, reviewer qualification,
or clinical utility. Confidence and uncertainty remain unavailable (null).

Both `clinical_gate_authorized` and `training_release_authorized` remain false.
The frozen CNN checkpoint is unchanged and its evaluation remains separate from
the geometric benchmark. No database, staging service, Testing split or deployment
was accessed for this increment. Release blockers in the prior report still apply,
including current-schema backup/restore, migrations and controlled staging approval.

**Demonstration recommendation:** acceptable only as a synthetic software/research
workflow, with the synthetic notice visible and the weak CNN result, generator-only
metrics, unavailable confidence, and absence of expert/clinical validation stated.
Do not demonstrate it as patient-case stenosis analysis or as a completed clinical
Milestone 3 outcome.

---

## Continuation gate — 24 November 2026

**Still not ready to publish or deploy.** Fresh frontend checks pass (650 tests,
lint and build); the available PostgreSQL suite passes (881 passed, 13 skipped,
3 warnings) on disposable QA. Nine SciPy-dependent research modules and three
Torch-dependent tests remain outside that suite; some are documented opt-in tests.

The candidate had 164 changed paths (37 modified, 127 untracked) before staging; all 164 are now staged locally.
A documentation file embeds a real-CT viewer screenshot supplied by the project
owner. Since GitHub is public, do not transmit that image until its exact source and
redistribution authorization are confirmed. Machine-specific checkpoint paths in
the segmentation README have been replaced with portable private-artifact guidance.

Staging was last recorded at schema 0010 while this source adds migrations through
0016. The retained backup was recorded at schema 0009 and is stale. Do not update
the running Docker stack until a fresh coordinated database/private-storage backup
and isolated restore pass, migrations are reviewed, and a maintenance window with
paused/drained writers is reconfirmed. No staging container, image or database was
changed in this continuation.

## Final engineering verdict ? NOT READY FOR DEPLOYMENT

Updated 24 November 2026. Evidence: `final-engineering-20261124T093721Z`.
Branch `codex/milestone3-review`; HEAD remains `e37b7c87eebe5099686687eacd6a6db897d2e6c7`.
All changes remain local and all 164 paths are staged. No commit, push, merge, staging migration or deployment has occurred.

Local research/reviewer increments are verified within their declared bounds.
Frontend 649, scientific 211, PostgreSQL 874/13 skipped, browser 216/3 skipped,
API 25, actual-API 3, SQLite 76/3 skipped and synthetic restore 1 passed. Suites overlap.

Fresh read-only inspection: running API/web source label b47d74aba0daf0a7ecbe7dd5ec6141b6726a6f36;
staging DB revision 0010_case_reviews; health/readiness 200; protected reads without
credentials 401; new review route 404. API/PostgreSQL have no host-published ports;
web publication remains loopback-only. Required secret/database configuration is
present; values were not printed. This is not an independent full secrets audit.

Retained 0009 backup hashes, safe archive reading, pg_restore list and allowed ACLs
pass. It is stale for staging 0010. Fresh synthetic 0015 dump/restore passes in the
pinned disposable QA instance; it does not establish current operational backup,
private-volume ACL/xattr recovery or a deployment rollback rehearsal.

Required before release: independent source/security review; current coordinated
real DB/private-storage backup and isolated restoration; approved immutable source/
image identity; migration handling from actual 0010 to unchanged source head 0015;
compatible recovery preserving reviewer isolation/immutable evidence; explicit
approval and staging role-by-role rehearsal. Do not automatically reconnect an older
API that lacks account isolation after assignments exist. Do not downgrade/delete
new review records as rollback.

General centerlines, expert lesion supervision, trained stenosis/severity/XAI and
real reviewer qualification remain unresolved. Full packet receipts and amendment/
reassignment/withdrawal lifecycle are still incomplete engineering/protocol work.
No unsafe transitions or fake qualifications were added to claim completion.
Both clinical_gate_authorized and training_release_authorized remain false.

No staging mutation, migration, backup creation, restore, deployment, commit or push
was performed. Latest source stays local. The documentation is evidence of software
progress, not permission for clinical use or production release.

---

## Prior entries (preserved)

## Latest state ? local verification passed; deployment NOT APPROVED

24 November 2026; increment `m3-browser-centerlines-20261124T082756Z`.
Current source remains local at the unchanged review HEAD; all 164 pending paths are staged. New offline
research routes/UI and documentation are not deployed. No real database migration,
backup, restore or staging change was performed.

Fresh evidence: 636 frontend tests; 868 PostgreSQL passed/12 skipped; 178 separate
scientific tests; 22 new API tests; 1 actual-API research browser test; 213 browser
passed/3 skipped. Build/lint/diff pass with documented warnings. These are software
checks, not clinical validation or a current full staging rehearsal.

The new route needs the existing scientific runtime to recompute evidence and exact
producer/server implementation/environment identity. It admits one verification per
process; it is not a distributed rate limit or hard CPU deadline. Multi-worker
resource/security review remains necessary before exposing it. Unavailable runtime,
capacity or busy states fail explicitly. Original viewer caps and blinded routes
remain unchanged. No new schema migration/dependency/lockfile/gate was introduced.

General automatic branches remain unresolved; supplied source-bound branches are
required. Expert lesion supervision, trained stenosis classifier, clinical severity,
calibrated confidence and genuine stenosis attribution remain unavailable. Both
clinical_gate_authorized and training_release_authorized stay false, including R3
and adjudication. The documentation distinguishes engineering progress from these
clinical/external blockers.

Before release: independent source review; current coordinated staging DB/private
storage backup and isolated restore; approved immutable source/image identity;
reviewed migration handling from actual staging baseline; preserve CT-only access
and immutable evidence during recovery; explicit deployment approval and rehearsal.
Historical schema-0009 backup does not prove current schema-0010/new-review backup
readiness. Do not reconnect an older API lacking review isolation after assignments.

Verdict remains **NOT READY FOR DEPLOYMENT**. No commit, push, merge or deployment.

---

## Historical entries (preserved)

Updated 24 November 2026 11:14 IST. Local increment `m3-completion-20261124T051538Z`; branch/HEAD unchanged. No commit, push, merge, staging migration or deployment.

## Latest state: research increment verified, deployment still unapproved

The previously blocked disposable PostgreSQL check is resolved: the exact pinned QA
container was restarted and 868 tests passed (10 documented skips). Actual-API
reviewer rehearsal passed. Frontend 622, browser 211 (3 skipped), separate research
backend 119, build/lint/diff checks passed. Staging was not restarted or modified.

The new offline native-mask scanner and source-linked calculation visualizations
are verified for their supported research scope. No new API, migration, dependency,
clinical gate, training release or stenosis model was registered. Source hashes,
exact numerical geometry, code identities and dependency versions are retained.

Release remains **NOT READY FOR DEPLOYMENT**. Review the uncommitted source; preserve
blinded access during rollback; verify real deployment images and approved data;
prepare current-schema coordinated backup/restore; obtain explicit migration and
deployment approval. No fresh staging backup/migration/deployment was attempted.

Remaining M3 limitations: supplied branches are mandatory, native mask storage and
frontier budgets are enforced, browser large-mask/oblique rendering is still bounded,
mask units must be explicit, and CT/mask numerical agreement does not prove anatomy.
The source plan's split statement is an operator declaration, not a dataset/licence
attestation. Actual Training membership must be independently verified before use.
ImageCAS CC BY-NC 4.0 restrictions remain preserved. No restricted dataset was used.

There is no verified clinical lesion supervision, trained stenosis classifier,
validated severity/percentage output, calibrated confidence or stenosis attribution.
Local simulated records are not expert labels or trusted immutable AI submissions.
Both clinical_gate_authorized and training_release_authorized remain false.

## 2026-11-25 synthetic model experiment

An optional, non-deployed synthetic-only 3D CNN was trained in an isolated CPU environment and has a real held-out synthetic result (0.31 accuracy, macro-F1 0.3076, n=100). Its weak metrics and synthetic-only distribution make it unsuitable for patients. Inference requires the supplied phantom to reproduce byte-for-byte from the generator; it is not registered as a clinical or case-analysis provider. 3D Grad-CAM is available only on those generated phantoms. No API, database, frontend, Docker image, staging deployment, clinical gate or training-release authorization changed. This does not clear any release blocker or complete Milestone 3.


---

## Prior sprint evidence (historical, preserved)

Updated 24 November 2026 10:15 IST. Evidence: external run `ai-assisted-m3-20261124T042751Z`. Branch and HEAD unchanged. All new work remains local, unstaged and undeployed.

## Latest research increment: local verification only

Verdict remains **NOT READY FOR DEPLOYMENT**. A source-bound local provisional
research workbench was added and verified: 607 frontend, 25 browser, 39 profile/schema
and 29 pure quantitative-gate tests passed; build/lint/diff checks passed. Existing
warning messages remain documented. Pinned PostgreSQL tests could not execute while
the QA container is stopped; no environment restart was attempted.

This is a safe demonstrable software subset, not completion of clinical Milestone 3.
Available lumen masks/centerlines do not provide verified lesion-level labels. No
stenosis model was trained. No fabricated AI/expert labels, calibrated confidence,
severity or attribution were created. Grad-CAM investigation is documented in
`docs/provisional-research-assessments.md`; the source-bound profile trace is geometric
support, not a model attribution map. Restricted dataset contents were not accessed.

R1/R2/R3 here are distinct deterministic research procedures on shared evidence,
not qualified independent reviewers or three AI models. Frozen local snapshots and
hash-linked downloads are not durable authenticated immutable submissions. They stay
outside human-review persistence, clinical reports, evaluation metrics and training.
Clinical and training-release flags remain false in every generated record/state.

M1 foundations/docs and M2 comparison/checkpoints remain unchanged. M4 review
implementation and migrations remain unchanged. No new backend route, migration,
dependency/lockfile update, checkpoint, evaluation record or data release was made.

Previously inspected staging/backup blockers below are still unresolved; staging
was not freshly queried or changed during this research increment. The latest local
source has not been built into/deployed as a staging image. No commit, push, merge,
backup, restore, real migration or deployment occurred. Release requires independent
source review, usable QA PostgreSQL, current-schema coordinated backup/restore,
approved immutable source/image identity and explicit operational approval.


---

## Previous completed sprint evidence (retained; not a fresh rerun)

Updated 24 November 2026 09:41 IST. Branch `codex/milestone3-review`; base HEAD `e37b7c87eebe5099686687eacd6a6db897d2e6c7`. New code is uncommitted and undeployed. External evidence run: `completion-sprint-20261123T171203Z`.

Verdict: **NOT READY FOR DEPLOYMENT**. Local software/comparison verification is
complete for the reported scope, not clinical approval or deployment permission.

## Verified preparation

- 50 predictions/model, 100 native-grid saved masks independently checked; repeat
  report hashes match. Original references/checkpoints/evaluations preserved.
- 4B/4C/4D core review software, source/owner binding, isolation, immutable submissions
  and credential-gated hash-linked adjudication tested.
- Frontend 572 passed; available PG 868 passed/10 skipped; browser 208 passed/3 skipped;
  actual-API synthetic reviewer rehearsal and populated migration/restore checks passed.
- Architecture, wireframes, Help, checklist and evidence updated.

## Fresh staging/backup inspection

Existing API/web/DB healthy; health/readiness 200. Live schema is 0010_case_reviews;
new reviewer routes absent. Local source is not deployed. Web is loopback-published;
API/DB have no host-published ports. No live oversized upload was sent.

Pending migrations: **0011 through 0015**. They were applied only in disposable QA.
Migration 0010-0012 bytes are unchanged. Upgrades add tables/guards without transforming
existing domain rows; downgrades destroy new review data and are not automatic rollback.

Retained verified backup is **0009**, stale for live **0010**. Hash/list/archive/ACL
checks pass; historical restore evidence does not cover current schema or prove
fresh private-storage recovery. Writers were not paused and no fresh real backup
was created. Current-0010-aware backup tooling and a maintenance window are required.

## Before release approval

1. Independently review dirty source/migrations; approve a precise immutable release
   commit/image identity. No commit/build/deploy is implied by this report.
2. Verify optional MONAI dependencies/checkpoint/serving behavior in the approved
   candidate image. Saved Kaggle results do not close skipped local runtime tests.
3. Approve reviewed current-schema backup tooling/window; explicitly pause/drain real
   writers. Create and verify coordinated PostgreSQL/private-storage backups,
   ownership/permissions/ACL/xattrs, all schema objects/sequences and disposable restore.
4. Separately approve migration 0011-0015 and deployment. Preserve data/volumes/images;
   verify routes, health, roles, case preservation, source hashes and review isolation.
5. Rehearse controlled demonstration with authorized real records and honest empty/
   unavailable states. Passing source tests does not establish staging UI availability.

## Recovery and clinical blockers

After assignments exist, an old API without the review-isolation guard would restore
legacy AI/case access and compromise blinding. Do not simply reconnect old images.
Recovery must retain restrictions and immutable evidence through a separately
approved compatible procedure. No automatic downgrade or restore is authorized.

Real qualified reviewers, verified human independence and full expert-packet
inventory/evidence/coverage/signoff integration remain incomplete. No real credential
is seeded or self-certified. Adjudication never enables clinical or training release.
No clinical stenosis classifier, validated severity/percentage or genuine stenosis
XAI is established. Testing remains held out. Embedded third-reader CT and versioned
amendment/reassignment are not implemented; verified CT download is available.
Host privacy/remote-access assumptions were not resolved by loopback Docker checks.

## 2026-11-25 local-only addition

A structured, authenticated PDF research-report endpoint and browser download are implemented and locally verified with synthetic fixtures. The output is generated from the backend report snapshot, not webpage printing; it does not include CT/overlay figures because the structured report source exposes no image payload. This change remains unstaged/undeployed relative to the existing staged snapshot; no release or staging readiness is implied. The broader UI/UX audit is still outstanding, and clinical stenosis functionality remains blocked by missing qualified lesion supervision and validation.

## 2026-11-25 synthetic experimental workbench

The separate synthetic-only stenosis workbench is locally integrated but not release-verified. It requires an operator-configured external synthetic checkpoint path and matching SHA-256; with no configuration the API reports model inference unavailable while synthetic sample generation remains available. The current checkpoint is weak on a synthetic held-out set and must not be presented as a useful classifier. Browser tests used mocked API responses. Six focused isolated API/model tests passed with the pre-existing temporary PyTorch environment; the normal backend pytest setup is blocked because `reportlab` is missing in the available worktree interpreter. No Docker image was built and no deployment occurred. Release remains blocked pending dependency-complete full backend verification, security/runtime review, and ordinary deployment approval. Clinical validation and training-release flags remain false.

## Milestone 3 data blocker update - 2026-11-25

Primary-source review confirms the current model blocker: no verified, authorized 3D CTA lesion-level dataset is available in this worktree. ASOCA files require owner permission through UK Data Service; Zenodo 4638863 files require ethics approval/waiver evidence; ARCADE is 2D X-ray and its Zenodo record has no visible license declaration. No restricted files were accessed and no license assumptions were made. The offline geometry research workbench remains separate from clinical case analysis. Keep `clinical_gate_authorized=false` and `training_release_authorized=false`.

## Release status update — 25 Nov 2026

**Not release-ready for clinical use or deployment.** Current M3 work demonstrates a separate synthetic-only research workflow. A 180-phantom controlled detector benchmark and a 500-phantom frozen-model evaluation are reproducible, but the CNN macro-F1 is 0.2887 on its synthetic test split and the generator-informed baseline is not a fair real-world comparator. The checkpoint is unchanged and is not connected to case APIs.

Verification passed for the available SQLite backend suite (1006 passed; 197 PostgreSQL-only skips), frontend unit suite (658), full browser suite (221 passed; 3 explicit real-volume skips), and two real local API/browser configurations (checkpoint available/unavailable). Lint/build passed with warnings listed in `TEST_EVIDENCE.md`. The live API test used only a new disposable local SQLite database and synthetic phantom input.

M3 remains blocked on qualified lesion-level labels/independent review and clinical validation. No patient-volume stenosis prediction, clinically meaningful percentage/severity, calibrated confidence or clinical XAI exists. PostgreSQL-specific tests, current staging backup/restore freshness, release build identity, and staging rehearsal remain unverified here. No deployment was performed. Preserve `clinical_gate_authorized=false` and `training_release_authorized=false` in any future release.


## Final M3 audit note ? 25 November 2026

The synthetic-only M3 integration passed the available current-source unit/browser/build checks (backend 997 passed / 198 skipped / 2 warnings; frontend 662 passed; browser 221 passed / 4 gated skips; lint and build exit 0). PostgreSQL-only and Torch-dependent runtime behavior was not fully exercised in this audit. This does not change the release decision: no clinical deployment or patient-case stenosis demonstration is authorized or supported. Both clinical and training authorization flags remain false. M1/M2/M4 are not recertified here.

## 25 Nov 2026 — separate real-volume research QC increment

An authenticated, non-persistent endpoint was added at `POST /api/v1/experimental-stenosis/real-volume/analyze`. It accepts only a 3D `.nii`/`.nii.gz` CT and a matching binary 0/1 segmentation mask; both are size-bounded and validated for complete NIfTI payload, finite voxel values, equal dimensions, valid affines, affine alignment and compatible declared units. Temporary upload files are deleted after processing. The response records CT and mask-file SHA-256, native shape/orientation/spacing, RAS-mm spacing and a CT-bound geometry fingerprint when CT units support conversion.

The response reports foreground voxel/component counts and, only for physical geometry and masks no larger than 4 million voxels, attempts the existing conservative experimental branch-graph extractor. The graph may abstain on topology, thinning or support checks; it is a digital skeleton diagnostic, not a validated anatomical centerline. The general input cap is 67,108,864 spatial voxels; automatic graph extraction has the stricter 4,000,000-voxel cap.

Crucially, uploaded mask semantics are not source-attested. The ImageCAS audit identifies coronary artery segmentation masks, not lumen or lesion labels, and records unresolved mask units. Therefore the API returns no lesion candidates, no cross-sectional lumen profile, null reference/minimum lumen measurements, null percentage narrowing and null provisional severity. It never calls the synthetic CNN or Grad-CAM, persists no case/result, and enforces `clinical_validation=false`, `clinical_gate_authorized=false`, `training_release_authorized=false`. This completes a bounded real-volume input/QC and topology demonstration only; stenosis detection and measurement remain unavailable until a suitable source and its lumen semantics are independently verified.

Fresh checks: backend focused tests **17 passed, 1 skipped** (optional synthetic Torch-runtime test); frontend unit suite **664 passed**; focused browser workflow **5 passed**; Python compile, frontend production build, lint and staged/unstaged `git diff --check` exited 0. Lint reported three existing warnings (AuthContext and synthetic page); build reported the existing large NIfTI/runtime chunks. Browser testing used mocked API responses; API tests used temporary NIfTI fixtures and role dependency overrides, not a live database. No original dataset file, patient data, staging, database, model checkpoint, or Docker resource was accessed. The 164 staged paths, branch and HEAD were preserved; no files were staged or committed.

Final verification addendum (25 Nov 2026): after adding authorization-change invalidation coverage, the focused browser suite completed **6/6 passed**. The full application OpenAPI was generated under temporary test-only settings with warnings treated as errors and included `POST /api/v1/experimental-stenosis/real-volume/analyze` with unique operation ID `analyze_real_volume_research_upload`. The backend focused result remains **17 passed, 1 skipped**; the skip is the optional synthetic PyTorch runtime check. No patient, staging or production database was connected.
