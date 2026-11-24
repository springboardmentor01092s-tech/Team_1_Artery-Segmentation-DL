# Offline profile evidence — provisional research only

## Final engineering extension — 24 November 2026

The supported API/browser demonstration now also uses a 129 × 129 × 257 synthetic
source (4,276,737 voxels), above the small-mask preview limit. Actual-API tests verify
recomputation, CT navigation and export/restore without a mask/probability download.
This does not establish larger original clinical volumes or the maximum configured cap.

`GET /api/v1/cases/{case_id}/segmentations/{result_id}/research-evidence/identity`
returns private/no-store current mask-byte identity and allowed run metadata. It
rechecks session/metadata after hashing. Assigned CT-only accounts remain denied.
The workbench rechecks on focus and every 60 seconds while idle; source/access
failure removes the loaded profile and CT. Export/navigation still fully recompute
profiles. No full mask enters browser memory merely to display evidence.

Restricted trees can now produce offline profile plans through the
[automatic branch bridge](automatic-branch-research.md). General extraction,
larger automatic masks and unsupported browser oblique geometry remain unresolved.

---

Implemented locally on `codex/milestone3-review`, base
`e37b7c87eebe5099686687eacd6a6db897d2e6c7`. No deployment, new migration,
clinical gate, training release or stenosis inference is introduced.

## Format and trust boundary

The existing bounded offline producer now additionally emits `browser-evidence.json`:

- `schema_version`: `offline-research-evidence/0.1`.
- `plan_json`: the exact UTF-8 plan text, preserving its SHA-256 identity.
- `record`: the actual `full-volume-research-profile/0.1` output.

This contains source CT/file-mask/canonical-mask SHA-256, exact native shape and
affine, geometry fingerprint, explicitly supplied ordered branches, branch and
parameter fingerprints, all sample/candidate evidence, implementation hashes,
procedure versions and dependency versions. No input path supplied by this JSON
is used to select a server file. Both release flags must be false.

The offline plan declares `Training` or `synthetic`. That declaration is not a
dataset licence or authoritative split attestation. Independently check actual
Training membership and use rights before processing real files. No Validation
or Testing case was used for this demonstration.

## Authenticated verification

`POST /api/v1/cases/{case_id}/segmentations/{result_id}/research-evidence/verify`
accepts the literal JSON document, at most 2 MiB. The stream limit precedes JSON
parsing and authentication processing. Existing case-reader authentication and
the global CT-only reviewer allowlist apply; assigned blinded reviewers cannot
use this model-prediction path. This does not create another permission system.

The server resolves the original CT and prediction mask from existing case/run
records. It rejects unsafe paths and stale runs, recomputes the bounded profile
from those actual files in exclusive temporary scratch, then compares the entire
result with the input. This validates actual bytes, branch support, parameter
and implementation identities, every candidate/sample, geometry and procedure;
it does not trust an uploaded `verified`, hash or authorisation claim.

After computation it rechecks the current actor/session, run metadata, CT
freshness and uncached mask digest. Concurrent assignment creation is serialized
by the existing global review-access lock. Successful responses are `no-store`.
No evaluation, clinical result, job, human review, training label or persistent
research record is inserted. Temporary verification snapshots are removed.

Errors: 401 session; 403 blinded workflow; 404 absent case/run; 409 stale,
altered or incompatible evidence; 413 body size; 415 content type; 422 malformed
JSON; 503 optional scientific runtime, scratch capacity or busy verification.
Only one verification runs per API process. This is not a global distributed
rate limit, kernel memory cap or hard CPU deadline. Multi-worker deployment needs
resource/rate-limit review before exposure. Exact producer/server implementation
and environment matching intentionally rejects old or incompatible evidence.

## Browser procedure

1. Open a current saved run in **Cases → Segmentation**.
2. Choose **View offline research evidence**. This is separate from the ordinary
   **View CT + Segmentation** path and does not download a mask to display evidence.
3. Select the producer's `browser-evidence.json`. The authenticated server must
   verify it before any result is accepted.
4. Read the source hashes, two provisional procedures and R3 disagreement trace.
   They are deterministic algorithms sharing one profile, not three AI models or
   qualified independent human reviewers. Confidence and clinical severity remain
   unavailable. No anatomical proximal/distal direction is inferred.
5. Open the calculation evidence and locate a sample in the original CT. Optional
   CT navigation downloads only the protected original CT, verifies its bytes and
   geometry, and retains the original browser budgets/oblique refusal. If CT
   rendering is unsupported, the verified profile remains readable with coordinates
   for a suitable desktop viewer; no image is substituted.
6. Export the **read-only offline workspace**. Its format
   `offline-research-workspace/0.1` stores original evidence text and deterministic
   assessment SHA-256, with false authorizations. Restore and export reverify the
   real server sources and recompute assessment identity. The receipt is not a
   signature or durable attestation. A forged JSON object cannot manufacture the
   in-memory authenticated receipt used by the assessment constructor.

Pending operations are aborted and discarded after source/session changes. Loaded
evidence is cleared on session invalidation; same-window token changes are checked
before every operation and by a bounded freshness timer. Both ordinary report JSON
helpers refuse all offline research wrappers, including nested ones, before Blob
creation. The research workbench and its viewer are hidden in print.

## Reproducible synthetic verification

No patient findings or genuine model predictions are fabricated. The synthetic
stored run used for integration testing is explicitly software-test data.

- `backend/tests/test_offline_research_api.py`: actual file recomputation,
  permissions, tamper/source/session refusal, resource/stream failures.
- `backend/tests/test_offline_research_live.py`: opt-in real FastAPI/PostgreSQL
  and browser workflow with synthetic CT and stored synthetic prediction only.
- `frontend-react/tests/offline-research.test.js`: receipt identity, forged
  responses, stale sessions, replay and ordinary-export isolation.
- `frontend-react/tests/e2e/offline-research.spec.js`: synthetic transport/UI,
  CT navigation, accessible evidence, export/restore, print and delayed sessions.
- `frontend-react/tests/fixtures/offline-research-synthetic.json`: actual Python
  extractor output, not handwritten medical evidence. Exact code hashes mean a
  producer change requires deliberate regeneration and review.

## Automatic branches remain unresolved

The original graph implementation was inspected and preserved. Lee thinning,
6/26-connectivity checks, Euler topology, complete raw-edge partitioning,
ambiguous-junction rejection and source-support refusal remain unchanged.
The frozen 20-case matrix and instrumentation were not rerun or tuned.

Eight new small synthetic characterization probes independently evaluate native
coordinates and distances to sampled analytic curves. One Y-shaped tree is
accepted; straight, curved and noisy-spur probes abstain at support validation;
the even-width probe loses/ fragments its skeleton; loop/disconnected/boundary
probes are refused explicitly. Determinism/refusal tests pass, but general
automatic extraction is not established. Reported nearest-point maxima have
finite analytic sampling error and are not anatomical centerline validation.
Supplied, source-bound ordered branches remain required for supported workflows.

No stenosis classifier, calibrated confidence, severity model, clinical narrowing,
expert ground truth or genuine stenosis attribution was generated. Both clinical
and training authorizations remain false, including after R3 or human adjudication.
