# Research case analysis and review

`GET /api/v1/cases/{id}/workflow` is the authoritative current workflow view.
It verifies the latest saved segmentation against the current source, recorded
checkpoint/threshold and available output files. An ambiguous run order, missing
provenance, stale input, missing outputs or changed reviewed bytes fails closed.
The endpoint does not run inference or enable a quantitative capability.

Existing case readers can inspect this view and the latest 20 immutable review
records. Existing **Clinician/Admin** case writers may use
`POST /api/v1/cases/{id}/reviews` with:

```json
{
  "segmentation_result_id": "<actual current saved run UUID>",
  "outcome": "accepted_for_research",
  "note": null,
  "acknowledge_research_only": true
}
```

This is request-field documentation, not a runnable example or an invented record.
The alternative outcome `changes_requested` requires a nonblank de-identified
note (up to 1,000 characters). Reviewer ID, role, time and artifact fingerprints
come from authenticated/server records; client claims cannot supply them.

One immutable decision is permitted per saved run. An identical repeat by the
same reviewer is idempotent (200); a conflicting/competing decision is rejected
(409). A new/changed output requires a new saved run and review. Review history
remains visible when the current scan or latest run changes.

Workflow states are `pending`, `awaiting_review`, `complete` and
`changes_requested`. Model analysis is complete only for current available
evidence. Review completion records a decision; a request for changes does not
complete the case. `complete` means accepted **for research workflow only**.
It does not assert accurate segmentation, a clinical sign-off, stenosis detection,
severity, calibrated confidence or an approved quantitative measurement gate.
The acknowledgement is an actor's attestation, not automated proof that a human
visually inspected a particular volume.

Case status stored on the case is a workflow hint for lists. The canonical
workflow endpoint rechecks current evidence; the overview and report use this
verified state and show an unverified/error state when it cannot be retrieved.
Replacing a volume, changing CT modality or saving a new run invalidates the
stored completion hint. Direct filesystem changes are detected on an explicit
workflow check. Checksums reuse the existing file-version cache and assume
application-owned storage; this is not a hostile-storage tamper-proof system.

The overview exposes a research review form, current reviewer/time/outcome,
history and a guarded **Workflow JSON** download. History and report pages expose
the same read-only provenance. Existing JSON/CSV case exports remain metadata
summaries; Workflow JSON adds run/review fingerprints without clinical findings.

## Migration and verification

`0010_case_reviews` follows `0009_evaluations`. It adds the review table and a
composite uniqueness key on existing segmentation IDs/case IDs. It does not
transform/delete cases, inputs, segmentation rows or outputs. PostgreSQL must
briefly lock/index the existing segmentation table; SQLite uses Alembic batch
table reconstruction. Downgrade destroys **review history** only and must not be
run as automatic recovery. Existing case status hints are not rewritten during
upgrade/downgrade; absence of a current review never implies approval.

Do not apply this migration to a normal/local, staging or production database
without a separately approved migration procedure. Development verification uses
only isolated disposable test databases. No model or quantitative gate changes
are part of this feature.
