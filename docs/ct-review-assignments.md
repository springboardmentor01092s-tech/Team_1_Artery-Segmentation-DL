# Original-CT R1/R2 preparation

This records the Stage 3/4A preparation and viewer boundary. The later local
[formal annotation/submission/adjudication increment](independent-lesion-review.md)
adds separate unverified records; historical test counts below describe Stage 4A,
not the final sprint totals. No clinical or training gate is activated.

This is unverified research preparation, not expert stenosis ground truth.
`clinical_gate_authorized=false` and `training_release_authorized=false` are
required by the server and database. This preparation-note contract does not itself
submit or adjudicate annotations. No classifier, percentage narrowing, severity
prediction or clinical gate is implemented here.

## Coordinator workflow

An active, unassigned Admin uses **Assigned CT review** in the existing sidebar.
Choose a real case, inspect its original CT identity, select two distinct active
Clinician accounts, enter the actual protocol version and acknowledge the
limitations. The API derives original CT bytes/geometry from existing storage;
it does not accept a replacement source, geometry or clinical release claim.

Assignments permanently restrict the selected accounts to their own original-CT
review endpoints and own authentication/profile operations. Known previous
workspace access disqualifies an account. Do not create another account to
disguise a person's previous exposure. Absence of audit evidence does not prove
clinical qualification, human independence, or absence of outside knowledge.
Both qualification and reader-independence verification remain false.

The current coordinator picker displays existing cases and the first 500 users.
It never receives review notes. There is no withdrawal/reassignment or second
protocol round; one study is permitted per case. Plan real reviewer identities
and the protocol before assigning. Administration of exceptional retention or
source replacement requires a separately reviewed lifecycle, not direct edits.

## API contract

All paths below are under `/api/v1`, use existing bearer authentication/RBAC,
and return no-store private responses.

| Method/path | Access and fields |
| --- | --- |
| GET `/review-studies/source?case_id=…` | Unassigned Admin; actual CT SHA-256, native shape/affine/mm units and geometry identity |
| POST `/review-studies` | Unassigned Admin; `case_id`, distinct `r1_user_id`/`r2_user_id`, `expected_ct_sha256`, nonblank `protocol_version`, `acknowledge_unverified:true` |
| GET `/review-assignments?limit=20&offset=0` | Own assignments only; SQL owner filtering before pagination; limit 1–50, offset ≤1,000,000 |
| GET `/review-assignments/{id}` | Own assignment, bound CT/geometry/protocol and current-source status |
| GET `/review-assignments/{id}/source` | Exact original CT snapshot, checked against the frozen hash; no mask or prediction |
| GET `/review-assignments/{id}/draft` | Own private preparation notes; absent note explicitly has `exists:false`, revision 0 and empty notes |
| PUT `/review-assignments/{id}/draft` | `notes` (≤4,000 Unicode characters), `expected_revision`, and both authorization flags explicitly false; 201 first save, 200 update, 409 stale revision |

Wrong owner returns 404, including an Admin requesting someone else's note.
Assigned accounts receive 403 on legacy case/image/volume, segmentation,
prediction, workflow, evaluation, model, analytics, reporting, job, audit and
administration APIs. The restriction is application-wide, rather than UI-only,
and survives changing an assigned account's role to Admin. Unknown Stage 4
submission paths return 404 because no such routes are registered.

Every relevant registered legacy method/path is enumerated from actual OpenAPI
in the regression test and requested as both R1 and R2. PostgreSQL transaction
advisory locks in a fixed namespace drain earlier protected requests before
assignment; the separate access transaction survives endpoint commits and is
held through response completion. Prior workspace access is conservatively
recorded before executing a legacy endpoint, without URLs, notes, tokens or
response contents. Failed auditing denies access before that endpoint starts.
This does not revoke
copies already downloaded or prevent human collusion/alternate accounts.

## Reader UI

Open **Assigned CT review**, select an own assignment and explicitly load it.
Choose **Open blinded original CT viewer** to load the exact assigned original CT
into an embedded CT-only viewer. The dedicated worker verifies the original file
SHA-256, decodes it within existing bounds and compares native shape/affine/mm
units with assignment provenance before any image is displayed. Assignment and
source availability are checked before and after loading, on focus and every
60 seconds. A failed check hides the image and releases rendering resources.
Session changes, selection changes and closing abort pending operations.

The CT-only adapter attaches one grayscale CT volume, with drag-and-drop disabled.
It does not import the segmentation viewer, annotation/candidate/XAI layers or
call prediction, segmentation, result or other-reviewer APIs. Slice controls cover
axial/coronal/sagittal planes, window/level, zoom, pan and reset. Native IJK and RAS
crosshair readouts are display positions, not recorded lesions or measurements.
No clinical interpretation or anatomical registration validation is implied.

The checksum-verified original CT download remains available for a desktop viewer.
This new download endpoint caps stored file bytes at the lower of 512 MiB and
the existing configured volume-file limit, before copying or serving a snapshot.
The embedded viewer retains the existing 67,108,864-voxel/memory budget, coded-mm
geometry checks and refusal of unsupported oblique/sheared geometry. GPU or
resource failures offer the original download, never a substituted prediction.
The decoder is shared with the existing viewer without changing its bounds.
Only own unverified preparation notes are saved here. Formal lesion capture,
immutable submissions and adjudication are not part of this viewer implementation.

A 409 or uncertain save preserves local text and blocks another Save. Explicitly
reload the latest version and replace local notes after privately preserving any
unsaved text. Never retry automatically with a newer revision. Logout/login
restores own server data through an explicit load. Account, session and selection
changes cancel/ignore pending operations. No notes enter localStorage. If bound
CT bytes, case association or geometry change, download and saving fail closed.

The prediction-exposed Stage 1/2 worksheet and its local JSON compatibility
remain separate. Assigned accounts cannot use those legacy APIs. The new
`ct-review-note/0.1` document is also rejected by ordinary report/metadata JSON
exports; it is not an evaluation record or a training/clinical label.

## Migration and verification limits

New migration `0012_ct_review_assignments` follows unchanged 0011 and 0010.
It adds `review_studies`, `review_assignments`, and `review_note_drafts`, restrictive
foreign keys, distinct-slot/reader constraints, an owner lookup index, false-release
checks, frozen-binding triggers and private-note author/revision guards.
No existing application data is transformed. Downgrade deletes all three new
tables and is destructive to preparation records; it is not routine rollback.

The production concurrency guarantee is PostgreSQL-specific. SQLite exercises
schema/validation behavior, but cannot demonstrate PostgreSQL advisory locking.
Migration/concurrency tests use disposable PostgreSQL schemas, synthetic CT and
separately identified synthetic accounts. No real annotations or qualifications
are created. Do not use this code before separately reviewing and applying the
new migration in the intended environment. Staging is not migrated by this task.
