# Independent lesion review — unverified research workflow

This local implementation adds manual review software, not a stenosis model or
expert ground truth. `clinical_gate_authorized=false` and
`training_release_authorized=false` are enforced throughout. No real reviewer
credential, lesion label, percentage, severity or clinical conclusion is seeded.

## Source and privacy boundaries

Existing Admin coordination assigns two distinct active Clinician accounts to an
original CT, its SHA-256, native shape/affine, geometry fingerprint and protocol.
Known prior workspace exposure is disqualifying. R1/R2 accounts are restricted
globally to their own CT-only routes, including when a later role change occurs.
They cannot fetch legacy images, segmentations, probabilities, evaluations,
reports, model/AI outputs or another reader's draft/submission. Real human
independence and qualification still require separate verification.

The embedded viewer retains its existing resource bounds and refusal of unsupported
oblique/sheared geometry. Seven landmark fields use the original native IJK grid:
center, proximal/distal boundaries and the two endpoints of each manual caliper.
Capture uses the full affine inverse. A non-null diameter needs explicit endpoints,
method and evidence; software does not calculate it. Missing values retain reasons.
Percentage and severity must remain null in this workflow. No finding is inferred
from a mask, centerline or screenshot.

If the initial display resource/hardware check refuses a volume, the source-bound
worksheet remains available with explicit manual native-IJK entry for an approved
external viewer. The authenticated original CT download verifies its checksum.
Apply each point before saving; unapplied input is not stored. The same geometry,
source freshness, owner and session checks apply. This fallback does not raise the
viewer budget, render an unsupported image, or expose a worksheet after an image
checksum/geometry integrity failure.

This is a bounded CT-only preparation projection of the external lesion-review
packet, not an import of a completed expert annotation under that packet's full
schema. Artery/segment, seven native landmarks, manual diameters, method/evidence
text and unavailable reasons are supported. The external packet's complete dataset
inventory/split binding, evidence-file receipts/hashes, diagnostic coverage,
qualification/protocol signoff and extra reference readings are not integrated as
verified clinical records here. Reference masks/centerlines remain external and are
not disclosed to blinded readers. Real case-to-packet mappings must be established
from actual CT identity; dataset IDs are not assumed to be application case IDs.

The overlay-exposed `lesion-annotation-workspace/0.1` JSON feature remains unchanged.
It cannot be imported as an independent CT-only reading. The new CT-only
`independent-lesion-review/0.1` format has its own source-bound JSON round trip;
cross-import is intentionally rejected rather than disguising prior AI exposure.

## Reviewer API

All paths below have the existing `/api/v1` prefix and existing JWT authentication.
Assigned owner checks also run inside the business transaction. GET responses are
private/no-store. JSON writes are bounded to 2 MiB before parsing, including
streamed requests without Content-Length.

| Operation | Endpoint | Contract |
|---|---|---|
| Read/save formal worksheet | `GET/PUT /review-assignments/{id}/annotation-draft` | `independent-lesion-review/0.1`; PUT `{document, expected_revision}`; 201 first save, 200 update |
| Version metadata | `GET /review-assignments/{id}/annotation-history` | Owner only; bounded limit/offset |
| Freeze independent review | `POST /review-assignments/{id}/submit` | `{expected_revision, expected_document_sha256, acknowledge_unverified:true}`; 201 first, 200 identical repeat |
| Read frozen review | `GET /review-assignments/{id}/submission` | Own immutable document, record/document hashes and source-current status |
| Coordinator catalogue | `GET /review-adjudication-catalogue` | Admin only; at most 100 studies/credentials, no review findings |
| Assign third reader | `POST /review-studies/{id}/adjudicator` | `{reviewer_id, credential_id, expected_source_sha256}`; both independent reviews must already be frozen |
| Own third-reader list | `GET /review-adjudications` | SQL owner/current-credential filter before bounded pagination |
| Third-reader detail/history | `GET /review-adjudications/{id}` | Both frozen parent records, their hashes, current original source and own version-chain metadata |
| Historical adjudication document | `GET /review-adjudications/{id}/versions/{revision}` | Owner/current-credential check; immutable document and hashes |
| Original CT | `GET /review-adjudications/{id}/source` | Verified original CT snapshot only; frontend also hashes downloaded bytes |
| Save adjudication | `PUT /review-adjudications/{id}/draft` | `{document, expected_revision}`; append-only version, never an overwrite |
| Freeze adjudication | `POST /review-adjudications/{id}/submit` | Saved revision/hash and explicit unverified acknowledgement; idempotent identical repeat |

401 means authentication/session failure; 403 means prohibited workflow/role;
another owner's assignment is 404 where the route itself is permitted; 409 means
stale revision, source/hash conflict, unavailable credential or immutable record;
422 means invalid annotation/correspondence. A conflict preserves browser edits and
requires explicit reload/resolve. An uncertain network response is not treated as a
successful save. Switching account/source cancels old asynchronous operations.

Local source-bound JSON export/restore remains separate from server persistence.
Unverified worksheets, submissions and adjudications are rejected by ordinary
clinical/report JSON exports before Blob creation. They are not joined into
evaluation metrics, clinical stenosis results or training data.

## Immutability and adjudication

Submission freezes the current formal worksheet and all historical versions.
Original submissions are retained. Third-reader assignment binds their immutable
IDs and record hashes. The third account must differ from coordinator and R1/R2;
it cannot become an independent reader. Its allowlist excludes legacy and R1/R2
workspaces. A current, separately verified credential is checked for each detail,
source read and write. Revocation/expiry prevents further evidence access.

There is deliberately no credential creation/self-attestation API. The credential
registry is empty in a fresh installation. Real credential evidence, its verifier,
scope and expiry need a separately approved human verification/registration
procedure. Synthetic QA-only credentials demonstrate software behavior; they
establish no real qualification. Do not insert a dummy credential to unblock use.

Adjudication stores manual correspondence between actual parent lesion IDs, field
decisions, evidence and unresolved outcomes. Unknown/duplicate lesion references
are rejected. All parent lesions must be accounted for at finalization. Differing
fields require explicit decisions; contradictory agreement is rejected. Unassessed
or ungradable parents cannot become agreement through adjudication. No consolidated
clinical label or calculated narrowing is produced. The third reviewer can download
the verified CT or use the embedded original-CT-only pane. It reuses slice,
window/level, zoom/pan and reset controls with a separate adjudication source loader.
Owner/current-credential, CT checksum/native geometry and frozen-parent bindings
are checked before/after loading. It has one volume, no overlays and no independent
reader worksheet. Session changes clear the private workspace; access/freshness
failures clear CT pixels. Existing resource/geometry limits remain unchanged.

Detail also supplies source/protocol/hash-bound documentation counts derived from
the frozen parents: lesion rows, seven landmark fields and manual diameters. They
are not anatomical coverage or correctness. External packet binding, evidence-file
receipts, protocol sign-off, real qualification and independence remain unverified.
Zero rows or an unassessed review never establish a negative clinical finding.
Lists/catalogues filter full existing credential prerequisites in SQL before
pagination, so ineligible records cannot affect page metadata.

Each draft save and final decision appends a version linked to the preceding record
hash. Final records cannot be edited/deleted. Concurrent writers serialize on the
assignment, with revision/hash checks; stale saves conflict. Amendments, reassignment
and post-submission withdrawal are intentionally unavailable until a separately
versioned, reviewed process exists. Privileged database administrators remain an
operational trust boundary; audit hashes are tamper-evident, not digital signatures.
Detail loads at most 50 recent chain-metadata entries and the latest document;
older immutable documents remain accessible by revision. Historical payloads are
not all loaded into memory on each page visit.

## Schema and deployment

- 0013 adds formal drafts and append-only annotation versions.
- 0014 adds immutable independent submissions and freezes their draft history.
- 0015 adds credential metadata, third-reader bindings and append-only adjudication.
- 0010, 0011 and 0012 remain unchanged by this increment.

Upgrades do not transform/delete existing domain data. PostgreSQL triggers add
immutability, actor/binding and no-release checks; PostgreSQL is authoritative for
concurrency tests. SQLite has reduced trigger coverage and is not evidence of
production concurrency safety. Downgrades destroy new review records and must not
be used as automatic application rollback.

These migrations have only been applied in disposable QA databases. Applying them
to any real local/staging database, deploying this source and credential registration
are separate operations requiring approval. Before deployment, quiesce writers and
validate a current coordinated database/private-storage backup and disposable restore
that includes all new tables, triggers, functions, sequences and files. The synthetic
schema restore test does not establish staging backup freshness or ACL/xattr recovery.
After reviewer assignments exist, rollback to an API lacking the account-isolation
guard is unsafe even though the schema additions are additive. Recovery must retain
the restrictions and immutable evidence; do not simply reconnect old images to the
live database or automatically downgrade/delete review records.
