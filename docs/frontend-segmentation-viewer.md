# CT and binary-segmentation viewer

Experimental research visualization — not for diagnostic use.

## Scope and existing work

The viewer is a research interface, not a diagnostic tool. This guide describes
public source behavior; it does not publish an operator's local backups, private
verification artifacts, database state or deployment details.

This integrates with the existing case `/cases/:id/analysis` workspace. Existing
run controls, authoritative history, authenticated downloads and role checks
remain. One selected CT/mask pair is loaded only after **View CT + Segmentation**.

## Setup and dependencies

Run `npm ci` in `frontend-react`, then the normal Vite or production build.
New exact runtime pins:

- `@niivue/niivue`: `0.69.0` (lazy-loaded, no React wrapper required).
- `nifti-reader-js`: `0.8.0` (worker/header validation).
- `fflate`: `0.8.3` (bounded worker gzip decompression).

The lockfile records transitive versions. Evaluate dependency upgrades against
the actual adapter and current tests; upstream documentation may describe a
different release. No dependency upgrade is implied by this guide.

References: [NiiVue repository](https://github.com/niivue/niivue),
[NVImage API](https://niivue.com/docs/api/nvimage/classes/NVImage/),
[NiiVue layouts](https://niivue.com/docs/layouts/).

No new runtime environment variables or model settings are required. Reuse
`VITE_API_URL` (default `/api/v1`) and the existing JWT client. Source verification
uses Web Crypto in a worker, requiring HTTPS or localhost. Keep signing keys and
database credentials private; Vite variables are public build-time configuration.

Optional model configuration uses VASCULAI_MODEL_CHECKPOINT for a trusted external
checkpoint; see the [model setup guide](../backend/app/services/segmentation/README.md).
No medical volume, weight, probability output or generated mesh is bundled. Hash
identity does not establish original training provenance or anatomical correctness.

## Additive source API

```http
GET /api/v1/cases/{case_id}/segmentations/{result_id}/source
Authorization: Bearer <current session>
```

The fixed source route is registered before the dynamic mask/probability route.
All four existing case-reader roles can read: Clinician, Researcher,
DataScientist, Admin. This preserves the current role-based case-access policy;
the repository does not implement per-patient ownership/tenant scoping.

Checks performed before streaming:

1. Existing authentication/active-user and server role dependencies.
2. Case exists and result belongs to exactly that case (404 otherwise).
3. Existing stale check: source path and persisted SHA-256 match the current
   application-owned source. Missing/unreadable/checksum-less sources fail closed
   with 409. Same-path byte changes invalidate the fingerprint cache.
4. Resolved source must remain directly within the private volume directory and
   exist as a regular NIfTI file. No caller-supplied filesystem path is accepted.

Responses preserve original file bytes. `.nii.gz` uses `application/gzip` and
`source_ct.nii.gz`; `.nii` uses `application/octet-stream` and `source_ct.nii`.
Headers include `Cache-Control: no-store` and `X-Content-Type-Options: nosniff`.
Reads record the normal audit event. No public static mount, path response field,
new table or migration is introduced. Existing result fields and artifact paths
are unchanged. OpenAPI advertises both binary MIME types and security.

The existing bounded fingerprint cache avoids rereading unchanged large files.
Cold/changed sources are hashed once per observable file version. It is not
tamper-proof against privileged storage changes that spoof every version field.
Application-owned immutable/versioned storage remains an operational assumption.

## Viewer workflow and controls

1. Open a case's Segmentation tab and select **View CT + Segmentation** on a
   current run. A stale run cannot open the viewer.
2. The viewer verifies current history, retrieves source and mask through the
   existing Axios bearer client, and shows actual bytes received for each file.
   It never follows server-supplied artifact URLs with credentials and does not
   load probability volumes by default.
3. A cancellable worker hashes the original CT download, checks the recorded
   source hash, decompresses gzip with an output limit, and validates payloads,
   CT/mask geometry and recorded inference provenance. History is checked again
   after loading to reject a replaced source during the transfer.
4. NiiVue displays axial, coronal and sagittal planes on a single canvas/context.
   Labelled keyboard-accessible sliders navigate anatomical slice indices;
   crosshair RAS positions, original dimensions and spacing are displayed.
5. Controls adjust CT window width/level in source intensity units, binary-mask
   visibility and opacity. Masks use a discrete magenta label LUT and nearest
   sampling. There is no smoothing, registration, threshold retuning or alteration
   of the stored prediction. Window changes are debounced to limit texture churn.
6. **3D binary mask** renders the actual saved mask volume, hiding CT density.
   It does not extract a surface mesh or invent centerlines/anatomy. Rotate with
   the pointer or the labelled left/right buttons; return to slices at any time.
7. Closing restores focus to the opener, aborts requests/worker work, removes
   observers/listeners, releases array references and explicitly loses the GL
   context. Retrying creates a fresh canvas/session. Error states preserve the
   authenticated artifact downloads as the fallback.

Session changes, navigation and run selection cancel or invalidate old loads.
History refresh closes stale/absent selections. While open, freshness is checked
on window focus and every 60 seconds; therefore a replacement in another session
may take up to that interval to be detected. This is not instantaneous push-based
invalidation. Closing the viewer does not cancel synchronous backend inference.

## Geometry policy

Both NIfTI-1 and NIfTI-2 single-file volumes are parsed. The mask must be unscaled
uint8 containing only 0/1. CT values remain in their original geometry and use
their NIfTI intensity scaling; model-normalized data are not displayed as CT.

The first implementation supports coded sform/qform, axis-aligned signed/permuted
spatial axes, anisotropic positive spacing and explicit millimetre units. It
rejects uncoded transforms, unknown/non-mm units, oblique/sheared or degenerate
geometry, nonfinite floating values, incomplete payloads and 4D input. This is a
viewer admission policy, not an alteration of the broader ingestion contract.
Unsupported studies remain downloadable for a suitable desktop application.

The selected affine matches nibabel `get_best_affine`: sform first, otherwise
qform. Both nifti-reader-js and NiiVue may otherwise prefer a larger qform code.
The validator reads original srow fields directly, and the adapter explicitly
sets the verified affine before rendering. Tests cover conflicting code values,
flips, translations and axis permutation. There is no manual array reslicing.

CT/mask shapes and affines must match, and CT geometry must match the selected
run's shape/affine/units. Affine comparison uses a small numerical tolerance
(`1e-4 + abs(value)*1e-6`). Spacing must agree with affine column lengths. A
matching affine alone does not prove identity: source SHA and server-side
case/result binding are checked independently. Mask artifacts rely on existing
UUID-owned, application-controlled result storage; no separate persisted mask
checksum was introduced.

Display convention is explicitly neurological. Slice controls follow RAS
anatomical axes rather than assuming original array indices are screen axes.
NiiVue supplies the world-space transforms and orientation markers.

## Performance limits and measured real-volume smoke

Admission limits are 67,108,864 voxels and an estimated 26 bytes/voxel CPU/GPU
working set. The heuristic budget is 768 MiB on devices reporting <=4 GiB RAM,
otherwise 1,536 MiB (8 GiB assumption when the browser does not expose RAM).
This is a resource heuristic, not a guarantee of available RAM/VRAM. GPU maximum
3D texture dimensions are checked before transfer. Transfers and decompression
are bounded at 512 MiB per artifact, with additional shape-derived output limits.
No silent downsampling is performed. Context loss/allocation failure shows a
fallback rather than substituting a fake image. Large volumes are fully loaded;
gzip NIfTI does not provide random slice streaming through ordinary byte ranges.

Device texture/memory limits and available RAM vary. Optional real-volume tests
require authorized external inputs with verified identities; no private performance
log or sample is a public setup prerequisite. Successful rendering on one machine
does not guarantee larger volumes or other browsers will fit. Preserve explicit
admission failures rather than silently downsampling or substituting data.

A plausible-looking or nonempty rendering is not evidence of segmentation accuracy,
calibrated confidence, stenosis, severity, diagnosis or clinical validation.

## Verification commands

```powershell
# frontend-react/
npm test
npm run build
npm run lint
# Use a supported Playwright browser in your own environment.
npm run test:e2e

# Optional real-volume smoke: explicitly supply de-identified validation artifacts.
$env:VASCULAI_VIEWER_REAL_CT = '<local validation CT path>'
$env:VASCULAI_VIEWER_REAL_MASK = '<matching saved binary mask path>'
$env:VASCULAI_VIEWER_REAL_METADATA = '<matching inference metadata.json path>'
npx playwright test tests/e2e/viewer-real-volume.spec.js --workers=1

# backend/, using the existing Python environment
python -m pytest -q --cov=app --cov-report=term-missing
python scripts/test_postgres.py --bin 'C:\Program Files\PostgreSQL\18\bin'
python scripts/test_frontend_contract.py
```

The real-volume test is skipped unless all three explicit paths are supplied.
Normal automated tests use synthetic data and disposable databases. No application
credentials or user records are used. The first compatibility spike renders real
synthetic NIfTI voxels/labels through WebGL and tests physical coordinates,
orientation, discrete overlay color and cleanup. Integrated tests cover protected
requests, gzip worker processing, source checksum, geometry failure, keyboard
navigation, opacity, windowing, 3D selection, focus, context loss on close,
cancellation, session changes, stale results, limited resources and mobile WCAG
checks. Unit tests also cover NIfTI-2 and qform-only headers.

Current setup and testing instructions are in the [project guide](../README.md).
Historical private handoffs/verification logs are not required and are not supplied.
Tests validate software contracts, not clinical or model-performance acceptance.

## Remaining scope

- Oblique/sheared transforms, non-mm/unknown units and uncoded-affine fallback
  require additional geometry work and test data before relaxing admission.
- No browser chunked/tiled streaming, surface-mesh extraction, GPU-memory query,
  durable backend inference queue, inference cancellation or push invalidation.
- Offline model/evaluation records have read APIs, but a completed model-comparison
  dashboard, dataset/split management, training, validated stenosis reporting and
  self-service email password reset are not implied by this viewer.
- Patient editing/deletion was not added: the existing backend exposes only
  registration/listing, and the UI accurately documents that limit. Existing
  case metadata updates, relationships, uploads, exports and admin APIs remain.
- First-Admin setup is now discoverable in Help: trusted operator command
  `python -m app.database.create_admin` from the backend environment. It prompts
  privately and refuses to promote existing accounts. No default credentials.
- Remote HTTPS hosting, production secrets, backups/restoration and a real
  production browser/API/model run remain operator deployment work.
