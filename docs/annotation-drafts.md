# Private annotation drafts

This document describes the overlay-exposed private preparation workflow. The
separate CT-only assignments, formal annotations, immutable submissions and
adjudication increment is documented in [independent lesion review](independent-lesion-review.md).
It does not turn these private drafts into blinded readings or clinical labels.

These endpoints persist **unverified reader preparation**, not clinical findings,
expert ground truth, independent readings, training labels or submitted reviews.
They do not change case completion, evaluations, segmentation outputs or gates.
Reviewer assignment, CT-only reading and adjudication are not implemented here.

## Access and source binding

Reuse normal bearer authentication. Only active `Clinician` and `Admin` users can
author or read drafts. Each draft is private to its actual authenticated owner;
another Admin has no implicit draft-content override. Existing case access allows
all authenticated case-reader roles to read cases; this feature does not invent
case ownership or create a second permission system.

The server binds each draft to the actual patient/case, original stored CT bytes
(SHA-256), native shape/affine/mm units and one saved segmentation run. It computes
a versioned geometry identity and records the run's checkpoint identity plus the
actual mask/probability hashes and threshold. The checkpoint identity comes from
the saved run record; this API neither loads nor validates checkpoint weights.
It rejects stale sources, unsupported/missing provenance and geometry mismatches.
Files must remain under application-controlled storage. Filesystem checks cannot
defend against a privileged storage administrator changing bytes after a check.

`clinical_gate_authorized=false` and `training_release_authorized=false` are
server-enforced in every response, request document and database row. Other
existing local-document validation/training/independence flags remain false too.
Manual values are never calculated or converted into clinical outputs.

## Routes

All paths below start with `/api/v1` and send `Cache-Control: no-store`.

| Method | Path | Request | Success |
|---|---|---|---|
| POST | `/cases/{case_id}/annotation-drafts` | `{"document": <local-document>}` | 201, revision 1 |
| GET | `/cases/{case_id}/annotation-drafts?segmentation_result_id=<uuid>&limit=20&offset=0` | None | 200, owner-only metadata page |
| GET | `/cases/{case_id}/annotation-drafts/{draft_id}` | None | 200, owner-only envelope |
| PUT | `/cases/{case_id}/annotation-drafts/{draft_id}` | `{"expected_revision": <integer>, "document": <local-document>}` | 200, revision +1 |
| DELETE | `/cases/{case_id}/annotation-drafts/{draft_id}?expected_revision=<integer>` | None | 204; only mutable owned drafts |

`local-document` is the current Stage 1 `lesion-annotation-workspace/0.1` document,
including all required false authorization flags. It is returned unchanged in
`document`, separately from server metadata. Use that member with the existing
local JSON restore/download helper; do not feed the whole server envelope to it.
The API does not silently repair old files lacking required fields.

The envelope contains `id`, `owner_id`, `patient_id`, `case_id`, `revision`,
`status=unverified_server_draft`, `source_current`, `source_unavailable_reason`,
`geometry_identity` (`version=ct-geometry/1.0`, SHA-256),
`segmentation_provenance`, `document`, creation/update timestamps and both false
release flags. Private storage paths are not returned.

Revision is an explicit optimistic concurrency token, not an advisory UI value.
Two transactions saving revision N cannot both succeed. A stale update/delete
returns **409** and never overwrites the winner. Retrieve the current revision
and let the author resolve changes; do not automatically retry an old payload
with a newer revision. No creation-idempotency contract is claimed.

Other responses: 401 unauthenticated/expired/revoked session; 403 disallowed
role; 404 wrong owner, case or draft; 409 changed/unverifiable source or binding;
413 request over 2 MiB, including streamed bodies; 422 malformed/unknown fields,
missing revisions, invalid geometry/landmarks or forged authorization flags.
Source-stale GET still returns the owner's original document with
`source_current=false` and an explicit reason. Saving is blocked, but the owner
can retrieve or delete the stale draft using its revision.

Discovery filters the authenticated owner and case in SQL before pagination;
the optional saved-run filter does not grant additional access. Pages expose
only the owner's draft IDs, revisions and source metadata, never worksheet
contents. Limit is 1–50 and offset is at most 1,000,000. A next offset never
exceeds that bound. Hidden records do not affect page metadata.

## Storage and transaction rules

Migration `0011_annotation_drafts` follows `0010_case_reviews` without rewriting
it or transforming existing data. One new table has restrictive foreign keys,
revision/status/release constraints, an owner index and write guards. Binding and
creation fields cannot be changed during an update; the database requires a
revision increment and refuses clinical/training flags or submitted status.

The API rechecks the current database user/session within the transaction.
PostgreSQL shared row locks preserve concurrent saves while serializing user
revocation and case/run changes; a revision-conditioned UPDATE determines the
winner. Document and audit event commit together. Source file versions are
checked again before commit. PostgreSQL tests use two distinct backend
connections synchronized after reading the same revision.

Downgrade **deletes all draft content**. It does not delete cases, reviews,
evaluations or uploads. Do not run it as routine rollback. Restrictive foreign
keys intentionally prevent deleting referenced cases, patients, owners or runs
until mutable drafts have been removed. A revoked/deactivated owner cannot use
the draft API; administrative retention/recovery is a separate future workflow.

No submitted record type or submission endpoint exists in this stage. Drafts
cannot be promoted or used to overwrite existing immutable research reviews.
Future submissions must use separate immutable records, not change this API's
mutable-draft semantics.

## Validation and limitations

The Python schema implements the Stage 1 source/geometry policy; production does
not execute JavaScript. Cross-language tests run the actual JavaScript validator
and Blob export helper against the server contract. Existing bounded NIfTI
validation and source-fingerprint utilities supply authoritative server evidence.
No viewer memory limits, source files, model parameters or clinical gates change.

The viewer has explicit private server Save/Load controls. Refresh the owner's
saved-draft list, select a record and load it to continue after logout/login.
Loading explicitly replaces local edits; downloading local JSON first preserves
an independent backup. Local JSON restore never saves to the server automatically.
A 409 preserves local edits and disables Save until an explicit reload/resolution
or separate-draft choice; it never retries with a newer revision automatically.
An unconfirmed creation blocks automatic retries and offers discovery or an
explicit separate-draft action, which may create a duplicate. These controls
recheck identity, source and immutable provenance before applying asynchronous
responses. No drafts or bearer credentials are added to browser persistence.
Drafts still require a saved segmentation run and disclose prediction exposure.
No blinding or reviewer qualification is claimed. Unsupported or oversized
volumes remain unavailable in the current browser viewer.

Original-CT R1/R2 preparation is a separate workflow; see
[CT review assignments](ct-review-assignments.md). Assigned readers cannot use
the prediction-exposed worksheet APIs. Neither workflow releases clinical or
training labels.
