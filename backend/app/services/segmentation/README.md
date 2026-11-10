# Experimental SmallUNet3D integration

This optional experimental service uses SmallUNet3D: base channels 8, 85,177
parameters, Conv3D/BatchNorm3D/ReLU blocks, two pooling levels, transposed
convolutions, skip connections and one-channel logits. The architecture and
inference integration were adapted from the project-supplied handoff with
owner-confirmed permission for this submission. See [attribution](../../../../ATTRIBUTION.md).

No weights or ImageCAS volumes are included. Original training-run identity and
optimizer-update provenance remain unresolved; a step-700 checkpoint label is not
proof of 700 updates. No full-dataset validation, clinical validation or advanced
model superiority is claimed. Historical aggregate handoff scores are not
reproduced as verified performance here. There is no training code in this service.
The loader uses weights_only=True, CPU mapping, finite-weight checks and strict
state loading, with no unrestricted pickle fallback.

### Viewer integration — 2026-10-19

The case Segmentation workspace now displays the original CT with the persisted
binary prediction and can volume-render that same mask in 3D. It does not change
model input, weights, thresholds or segmentation quality. The additive protected
`GET /api/v1/cases/{case_id}/segmentations/{result_id}/source` route uses the same
reader authorization and cached stale check as artifact downloads. It returns
original bytes with a generic filename and no-store caching. Existing response
fields and mask/probability routes remain unchanged; no new migration is needed.

The browser independently verifies the source SHA-256, checks CT/mask geometry
against run provenance, and refuses unknown/non-mm units, uncoded, oblique or
sheared transforms in this first viewer version. These are viewer restrictions,
not changes to ingestion or inference. Original downloads remain available.
See [the viewer guide](../../../../docs/frontend-segmentation-viewer.md).

## Setup and artifacts

Use the existing backend environment and install its normal dependencies first:

```powershell
python -m pip install -r requirements.txt
python -m pip install -r requirements-model.txt --index-url https://download.pytorch.org/whl/cpu
```

PyTorch is optional for the ordinary web APIs. Select a compatible official CPU
or CUDA wheel for your environment; CUDA availability is not inferred from a
configuration value. No package/checkpoint download occurs automatically at runtime.

Obtain authorized checkpoints, CTs and reference masks separately under their
applicable terms. Keep them outside this checkout. Verify complete SHA-256 values
against an approved provenance record before use. A hash identifies bytes, not
training history, anatomical registration or redistribution rights. No private
handoff, sample or validation report is a build prerequisite.

## Configuration

Copy/update `backend/.env` locally; `.env.example` contains all model settings.
`VASCULAI` is the exact spelling of these environment variables.

| Variable | Default | Meaning |
| --- | --- | --- |
| `VASCULAI_MODEL_CHECKPOINT` | unset | Existing trusted checkpoint path, absolute recommended |
| `VASCULAI_MODEL_THRESHOLD` | `0.70` | Binary foreground when probability >= threshold |
| `VASCULAI_MODEL_DEVICE` | `cpu` | `cpu`, `cuda`, or explicit `auto` |
| `VASCULAI_MODEL_BATCH_SIZE` | `1` | 1–16 patches; higher values require more RAM/VRAM |
| `VASCULAI_MODEL_THREADS` | `4` | CPU intra-op threads, 1–32 |
| `VASCULAI_MODEL_MAX_VOXELS` | `67108864` | Inference spatial voxel limit, additionally bounded by upload limit |
| `OUTPUT_DIR` | `./outputs` | Backend result storage, never a public static directory |

Select an authorized external checkpoint locally, without embedding its path:

```powershell
$checkpoint = Read-Host 'Path to an authorized checkpoint outside this checkout'
$env:VASCULAI_MODEL_CHECKPOINT = (Resolve-Path -LiteralPath $checkpoint).Path
Get-FileHash -LiteralPath $env:VASCULAI_MODEL_CHECKPOINT -Algorithm SHA256
```

Fresh installations apply the repository migration chain to head (currently
0009_evaluations); see the [backend setup guide](../../../README.md).
Existing databases require a reviewed backup and separately approved migration.
Downgrades can permanently delete segmentation/evaluation history; they are not a
default rollback. This guide does not attest to any operator's installed revision.

## Input, preprocessing and outputs

Only a **three-dimensional CT** NIfTI-1 or NIfTI-2 (`.nii` or `.nii.gz`) can be
segmented. Existing ingestion still accepts 3D/4D NIfTI; 4D inference is rejected
explicitly. DICOM remains unsupported, as do MRA and 2D-image inference. The API
requires case modality `CTA` or `CT Angiography`; modality is a user assertion,
not an automatic verification of HU calibration. CT values must already represent
the expected intensities. NIfTI slope/intercept is applied by the reader.

The existing bounded header/payload/geometry validation runs before voxel reads.
Inference additionally checks dimensions, resource limits and finite voxel data.
It preserves the handoff's exact algorithm:

1. Clip to `[-200, 800]`, normalize with `(image + 200) / 1000`.
2. Cover the original voxel axes with `64 × 64 × 64` patches, stride 32,
   explicitly covering the far boundary; zero-pad only axes shorter than 64.
3. Apply sigmoid independently to each patch's logits and **average overlapping
   probabilities**. No resampling or reorientation is introduced.
4. Crop padding, then use `probability >= threshold` for the uint8 binary mask.

Threshold 0.70 is an explicit configurable default based on the supplied
validation summary, rather than the handoff CLI's 0.50 default. This does not
establish an optimal or clinically validated threshold.

Each run writes a **new** directory containing:

- `probabilities.nii.gz`: float32 foreground probabilities, not calibrated clinical confidence.
- `prediction_mask.nii.gz`: uint8 values 0/1.
- `metadata.json`: checkpoint/source SHA-256, step, configuration, geometry,
  actual probability range, foreground count, elapsed time, limitations, and
  optional reference metrics.

Output dimensions, affine, qform/sform matrices and codes, voxel spacing, units,
NIfTI version and header extensions are preserved. Data dtype, intensity scaling
and display calibration are reset for probabilities/masks so CT scaling cannot
corrupt their values. Outputs inherit source header metadata: supply de-identified
inputs and handle outputs as protected study artifacts.

Reference annotations are optional CLI inputs. Their shape, affine and units must
match the CT, and foreground is **label > 0**. Dice is computed on the whole
sample with no smoothing; two empty masks yield 1. No reference is uploaded or
evaluated by the API in this phase.

Unknown reference spatial units remain a limitation even when dimensions,
affine and spacing agree. Matching geometry does not prove anatomical alignment.
Default evaluation refuses incompatible units. An explicitly approved diagnostic
override must retain the assumption and both unit declarations in provenance; it
must never bypass shape/affine/spacing checks or rewrite source headers.

## Standalone execution

From backend, inspect the supported interface with:

```powershell
python -m app.services.segmentation.inference --help
```

For a separately authorized run, supply your own external CT, trusted checkpoint
and unique external output directory. Keep the declared preprocessing, sampling
and threshold fixed for a reproducible experiment. Do not enable the reference-unit
override by default. No inference is authorized merely by reading this guide.
The CLI reads checkpoint/threshold environment defaults, not backend .env; other
options are explicit. Failures exit nonzero and outputs are never overwritten.

## Backend API contract

Existing case/image/volume endpoints and case status semantics are unchanged.
The new authenticated endpoints use the existing four-role policy:

| Endpoint | Access | Behavior |
| --- | --- | --- |
| `POST /api/v1/cases/{id}/segmentations` | Clinician/Admin | JSON `{}` or `{"threshold":0.70}`; synchronous inference, 201 only after output + DB persistence |
| `GET /api/v1/cases/{id}/segmentations` | All four case-reader roles | Run metadata/history, stale flag and authenticated download URLs |
| `GET /api/v1/cases/{id}/segmentations/{result_id}/mask` | All case readers | Protected uint8 NIfTI download |
| `GET /api/v1/cases/{id}/segmentations/{result_id}/probabilities` | All case readers | Protected float32 NIfTI download |

Responses contain `id`, `case_id`, `created_at`, `stale`, `metadata`, `mask_url`
and `probabilities_url`. Internal storage paths are not returned. Artifacts are
UUID-scoped, never served by a static upload/output mount, and downloaded with
`Cache-Control: no-store`. Authorization follows the repository's existing
role-wide case access; this phase does not introduce patient ownership rules.

Missing case/input is 404, invalid input 400, missing CT/modality or replaced input
409, request validation 422, missing runtime/checkpoint or busy worker 503,
execution/storage failure 500. Failed pre-commit runs are rolled back and their
owned output files removed. Original volume and checkpoint files are never
modified. Volume replacement marks prior runs stale; stale downloads are blocked.
Staleness also compares the persisted inference `metadata.source_sha256` with
the current source file's SHA-256, so changed bytes at the same path are detected.
Missing/unreadable inputs and legacy records without a source checksum are
treated as unverifiable: history returns `stale: true` and downloads return 409.
The response schema, metadata keys and endpoint paths are unchanged; this
strengthens the existing stale flag and 409 behavior rather than adding fields.

Checksum calculation is cached per API process for up to 128 file versions,
keyed by resolved path, device/file identity, byte size, and nanosecond modification
and change timestamps. Inference populates this cache. Ordinary history/download
requests stat the source and reuse its checksum; a changed version, cold worker
or cache eviction triggers one bounded-memory streaming rehash. Concurrent cold
reads are serialized, and changes during hashing or inference are rejected.
Touching a file without changing its bytes rechecks the hash but keeps results
current. No additional schema migration or checksum backfill is necessary because
the strong source hash already lives in result metadata.

The protected `GET /cases/{case_id}/segmentations/{result_id}/source` download
additionally makes a private `TemporaryFile` snapshot before sending any response
bytes. It copies in 1 MiB chunks from an open regular-file handle, enforces the
configured compressed or raw upload-byte limit, and checks the copied bytes'
SHA-256 against inference metadata. The existing freshness, role and containment
checks remain; the resolved path is checked again while snapshotting and the case
path is refreshed afterwards. The response reads only that same snapshot handle
in 64 KiB chunks and closes it on completion, disconnect/cancellation, or failure.
No source pathname is reopened by the response. Replacing the source or writing it
in place after snapshot validation cannot change the response bytes. A changed
copy fails closed with 409; no successful-read audit event is committed for it.

This source-only protection deliberately adds a full copy/hash and download-start
latency on every request, even with a warm fingerprint cache. RAM usage stays
bounded, but each concurrent download needs temporary disk space up to the
configured upload limit. The host must protect its temporary directory and have
sufficient disk capacity; temporary files can contain sensitive scan bytes and
are deleted on close. Python's temporary-file and open-handle APIs support Windows
without requiring POSIX `openat`, advisory locks or unlink-open-file semantics.
The source response retains the binary media type, safe attachment filename,
Content-Length, no-store/nosniff and audit logging. It serves full 200 responses;
FileResponse's automatic range/resume, ETag and Last-Modified behavior is no longer
advertised for this endpoint. Segmentation artifact downloads are unchanged.

This binds served bytes to the recorded checksum, not to an atomic database/filesystem
transaction: a new upload immediately after the final case refresh may still
overlap an already-authorized download of the verified original snapshot. Storage
must remain application-owned; this is not isolation from a privileged process
that can alter the private snapshot or database. It also does not claim to harden
the separate mask/probability FileResponse endpoints against pathname races.

The cache relies on observable filesystem changes and application-owned immutable
UUID uploads. It is not a defense against an actor rewriting bytes while forging
every cache-key attribute, and it is not a storage-integrity monitoring service.
Detecting such tampering without reads requires enforced immutable/versioned
storage; operators must keep upload storage private. Restart clears the cache.
Audit events are recorded for creation, listing and artifact access.

There is **one active inference per API process**, with immediate busy rejection.
This is synchronous research infrastructure: no durable queue, polling job API,
cancellation or cross-worker resource coordination. Use one API worker, budget
several GB of RAM and configure HTTP/proxy timeouts for actual CPU duration.
If a client times out, the server may still finish; inspect run history before
retrying. Storage retention and case-deletion orphan cleanup are operational
follow-ups; no deletion API is added. API/database health does not establish
model readiness.

The current authenticated Segmentation workspace retrieves authoritative saved
history and offers CT/mask slices and binary-mask 3D rendering; see the viewer
guide above. Rendering is not segmentation accuracy or clinical validation.
Quantitative stenosis, clinical severity/confidence and clinical findings remain
unavailable without a validated provider.

## Deployment and tests

The normal Docker image keeps inference optional. To include CPU PyTorch, use
`deploy/compose.model.yaml` alongside the existing Compose file; set
`MODEL_ARTIFACT_DIR` to the host directory containing the named checkpoint. The
overlay mounts it read-only at `/models`, sets the configurable model environment,
and enables the optional image build dependency. Apply the reviewed migration
before starting the API. Standard `/api/v1` and `/health` routing is preserved.
The current nginx timeout is 300 seconds; longer runs need an adjusted timeout or
a future background job worker. Images/full deployment must be tested on the
actual hosting environment; no production deployment is claimed here.

From `backend/`:

```powershell
python -B -m pytest -q -p no:cacheprovider
python scripts/test_postgres.py --help
python scripts/test_frontend_contract.py
python -m pip check
```

Tests use explicitly synthetic arrays/NIfTI fixtures. Optional original-checkpoint
tests require a separately authorized VASCULAI_TEST_CHECKPOINT and optional PyTorch;
ordinary web checks need neither. Never point tests at an application database.
The PostgreSQL helper provisions its own disposable cluster; inspect its arguments
and prerequisites before running it. No real sample is supplied with this snapshot.
