# Release readiness

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
