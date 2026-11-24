# VascuAI web implementation handoff — 2026-10-19

## Repository and preservation

Repository: `<REPOSITORY_ROOT>`.

Starting and final branch: **baseline-model-diagnostics**.
Starting and final HEAD: **461a7d1d3ee5047aa4dd5d37465f5c146e57230b**.
This is the existing commit, not a new implementation commit. All work is local,
unstaged and uncommitted. No branch switch occurred during this sprint.

The four initial tracked modifications were README.md,
frontend-react/src/components/AppShell.jsx,
frontend-react/src/pages/Landing.jsx and frontend/dashboard.html. Their existing
metric-honesty/research-only warnings were preserved. Before implementation,
copies, the binary Git diff, initial status and starting SHA were saved outside
the repository at `<REPOSITORY_ROOT>_codex_safety\web-sprint-20261019`.
AppShell, Landing and the static dashboard retain those pre-existing edits;
README additionally documents the new viewer.

The local model handoff remains intact. All eight original SHA256SUMS entries
were verified unchanged after testing. Checkpoint SHA-256:
`e208fa586bb9bb50dc77b913caa0355a547bad529f9f0d61df17880b2efc5254`.
The baseline is still 85,177 parameters, base 8, step 700, 64³ patches/stride 32,
clip [-200,800] then (image+200)/1000, default threshold 0.70. No segmentation
quality improvement or clinical validation is claimed.

## Features actually implemented and verified

1. Added protected original CT retrieval:
   `GET /api/v1/cases/{case_id}/segmentations/{result_id}/source`.
   It reuses existing case-reader authentication/RBAC, requires the result to
   belong to the case, reuses path + cached SHA-256 stale checks, validates
   resolved storage containment, rejects missing/unverifiable sources, and
   streams original `.nii`/`.nii.gz` with a generic filename, no-store and nosniff.
   Existing history fields and mask/probability routes are unchanged. No new
   migration or public static study mount was introduced.
2. Added an explicit **View CT + Segmentation** action in the existing case
   Segmentation workspace. The lazy viewer loads one selected pair through the
   shared Axios bearer client. It never follows returned artifact URLs with
   credentials and never loads probabilities by default.
3. A cancellable worker verifies the original CT SHA-256, performs bounded gzip
   decoding and validates NIfTI payload, CT/mask geometry and run provenance.
   Fresh history is checked before and after loading. Same-path/replaced sources
   fail closed. While open, freshness is checked on focus and every 60 seconds.
4. Implemented actual axial/coronal/sagittal CT slices with the binary mask,
   anatomical slice sliders, CT window/level, overlay visibility/opacity,
   orientation markers, dimensions, source-axis spacing and RAS positions.
   Default/click positions snap to voxel centres, including even-sized axes.
   All controls are keyboard accessible; opening/closing manages focus.
5. Implemented real **3D binary-mask volume rendering** with CT density hidden
   and pointer/keyboard-button rotation. No mesh extraction, smoothing, invented
   centerlines, stenosis markers or clinical findings were added.
6. Added memory/texture admission checks, binary transfer/output size limits,
   distinct transfer/checksum/decode/render phases, useful errors/retry/download
   fallbacks, cancellation on navigation/run/session changes, worker termination,
   observer/listener cleanup and explicit GPU-context release. Retry creates a
   fresh viewer canvas.
7. Added discoverable operator-only first-Admin instructions in Help. Existing
   bootstrap, public-registration restrictions and backend role checks remain.
   Updated the Imaging page to link to Segmentation instead of incorrectly
   claiming that all volume viewing is disconnected.
8. Reviewed existing real authentication, patients/cases, uploads, exports,
   settings and admin wiring. Existing operational contracts were preserved.
   Deliberately unavailable features were not replaced with fake controls/data.

## Viewer compatibility and geometry constraints

Exact new runtime pins: `@niivue/niivue@0.69.0`,
`nifti-reader-js@0.8.0`, `fflate@0.8.3`; package-lock updated. NiiVue is loaded
without a React wrapper. Vite optimization includes these dependencies to avoid
a first-use development reload. Final npm audit reports zero vulnerabilities.
No new production environment variables were introduced. Existing VITE_API_URL,
VITE_HEALTH_URL and VASCULAI_MODEL_CHECKPOINT configuration still applies.

The compatibility spike exercised real synthetic NIfTI rendering, nonidentity
affines, anisotropic spacing, an asymmetric binary landmark, three planes,
overlay pixels, physical coordinates and cleanup. Integrated tests cover
flipped/permuted axes. Unit tests also cover NIfTI-2 and qform-only input.

The initial viewer accepts explicit millimetre units and coded, axis-aligned
signed/permuted transforms. It rejects unknown/non-mm units, uncoded, oblique,
sheared or mismatched geometry, unsupported voxel types and 4D volumes rather
than guessing. Broader ingestion/inference support is unchanged and downloads
remain available for desktop imaging tools.

Both the parser and NiiVue otherwise may prefer a larger qform code, unlike the
backend's nibabel sform-first choice. The validator reads original srow fields
directly and the adapter applies the verified affine. Masks are discrete uint8
0/1 with nearest sampling. CT display uses original intensity scaling, not the
model-normalized input. Probabilities are never called calibrated confidence.

Resource limits: 67,108,864 voxels, heuristic 26 bytes/voxel working-set estimate,
768 MiB budget on devices reporting <=4 GiB RAM otherwise 1,536 MiB, and 512 MiB
per transfer/decompressed artifact plus shape-derived bounds. GPU texture limits
are checked. These are heuristics, not guarantees of available RAM/VRAM.
Web Crypto requires HTTPS or localhost. No silent downsampling is performed.

## Actual verification results

Final source has no known failing automated checks. Windows cannot create the
symlink needed for one test; its Linux equivalent passed in the container smoke.

| Command/check | Final actual result |
| --- | --- |
| `npm test` in frontend-react | **78 passed**, 0 failed |
| `npm run build` | **Passed**; warning for large lazy NiiVue chunk |
| `npm run lint` | **Passed**; one pre-existing AuthContext Fast Refresh warning |
| `npx playwright test --reporter=line` with supplied validation artifact paths | **53 passed**, 0 failed, 0 skipped |
| Normal browser suite without real artifact variables, prior final run | **52 passed**, real-volume test intentionally skipped |
| `python -m pytest -q --cov=app --cov-report=term-missing` in backend, original checkpoint enabled | **297 passed, 1 skipped**, 3 existing deprecation warnings; total coverage 93% |
| `python scripts/test_postgres.py --bin '<POSTGRESQL_BIN>'` | **297 passed, 1 skipped**, 3 warnings; isolated temporary cluster, coverage 92% |
| `python scripts/test_frontend_contract.py` | **3 passed**, real Axios/Uvicorn with disposable SQLite |
| `python -m pip check` | No broken requirements |
| `npm audit --omit=dev --audit-level=moderate` | Zero vulnerabilities |
| `git diff --check` | Passed; staged diff empty |
| Base Compose config, generated temporary validation values | Passed with `config --quiet` |
| Base + compose.model.yaml config | Passed with `config --quiet`; model directory read-only configuration |
| Core API and frontend Docker builds | Passed using separate sprint tags |
| Disposable Linux API/nginx container smoke | Passed: nginx syntax, health/readiness, SPA refresh, asset caching/404, API 401/404 forwarding, bearer forwarding, OpenAPI security/MIME types, real symlink escape rejected with 409 |

Browser tests use the existing Chromium executable:
`<LOCAL_TOOL_PATH>`.
No browser installation was needed. Synthetic fixtures cover accessibility at
desktop/mobile widths, keyboard navigation, failed authorization, stale history,
wrong source hash/geometry, cancellation, session changes, unsupported graphics,
limited memory, repeated navigation and context loss on close.

The final full browser run explicitly enabled these **test-only** variables:
`VASCULAI_VIEWER_REAL_CT`, `VASCULAI_VIEWER_REAL_MASK`,
`VASCULAI_VIEWER_REAL_METADATA`. They pointed to the existing de-identified
validation 851 artifacts. This did not run inference, touch test-set cases or
connect to the real application database. It served actual existing files via
isolated authenticated HTTP fixtures and exercised the real decoding/rendering.

That run rendered `(512,512,217)` CT/mask slices and genuine 3D mask successfully,
ready in **10,190 ms**. CDP backing storage samples peaked at approximately
**396.0 MiB** and dropped to **16.2 MiB** after close/GC. Initial backing storage
was about 10.8 MiB. AMD Radeon/ANGLE D3D11 reported max 3D texture size 2048 and
zero GL errors. GPU memory and browser-process total RSS are not measured by
those counters; results are not a guarantee for other devices/browsers.

Early iterations were not all green: tests identified affine-precedence and
initial voxel-centre issues, and a development optimizer reload; these were
fixed before the final passing run. The inactive-account test was corrected to
the existing 401 contract. The first container smoke used an unmigrated empty
throwaway DB and failed auth auditing; rerun with migrations confined to that
owned disposable DB passed. An initial fflate 0.8.2 audit finding was resolved
with the compatible 0.8.3 pin. None of these earlier failures is concealed as an
unexecuted check or an unresolved passing result.

## Docker/deployment scope

Docker Server 29.5.2 was available. Images were built as
`vascuai-web-sprint-api:20261019` and `vascuai-web-sprint-web:20261019`, avoiding
existing production tags. The final smoke uses a unique owned network and
containers, no host database or study mounts, generated temporary credentials
and an ephemeral SQLite schema solely for the test. Containers/network were
removed afterward. No production services were started or changed.

The model-enabled PyTorch container image, complete PostgreSQL Compose deployment,
remote domain/HTTPS, production secrets, persistent study mounts, backup/restore
and a real production browser/API/model transaction are **not verified** by this
sprint. Native isolated PostgreSQL tests and local unchanged-checkpoint tests
passed, but are not a substitute for that deployment acceptance run.

## Exact file inventory

Paths below are relative to `<REPOSITORY_ROOT>`. **No files deleted.**

Modified backend source/tests:

- backend/app/routers/segmentation.py
- backend/tests/test_segmentation_api.py

Created frontend source:

- frontend-react/src/components/SegmentationViewer.jsx
- frontend-react/src/lib/niivue-adapter.js
- frontend-react/src/lib/volume-geometry.js
- frontend-react/src/lib/volume-loader.js
- frontend-react/src/workers/volume.worker.js

Modified frontend/config:

- frontend-react/package.json
- frontend-react/package-lock.json
- frontend-react/src/api/segmentation-contract.js
- frontend-react/src/index.css
- frontend-react/src/pages/AnalysisResult.jsx
- frontend-react/src/pages/CaseDetail.jsx
- frontend-react/src/pages/Help.jsx
- frontend-react/vite.config.js
- frontend-react/src/components/AppShell.jsx — preserved initial edit
- frontend-react/src/pages/Landing.jsx — preserved initial edit
- frontend/dashboard.html — preserved initial metric-honesty edit

Created tests:

- frontend-react/tests/volume-viewer.test.js
- frontend-react/tests/e2e/nifti-fixture.js
- frontend-react/tests/e2e/viewer-spike.spec.js
- frontend-react/tests/e2e/volume-viewer.spec.js
- frontend-react/tests/e2e/viewer-real-volume.spec.js

Modified documentation:

- README.md — includes preserved initial warning
- backend/README.md
- backend/app/services/segmentation/README.md
- deploy/README.md
- docs/frontend-segmentation-ui.md
- docs/model-integration-verification.md
- docs/ui-features.md

Created documentation:

- docs/frontend-segmentation-viewer.md
- docs/codex-handoff-to-chatgpt.md

Expected final status is **20 modified tracked files and 12 untracked source/doc
files**, no staged changes/deletions. Generated builds, tests, medical images,
weights, caches and environments are ignored or outside the repository. The
final Git diff was reviewed, including all new untracked source files.

## Evidence locations outside Git

- Safety snapshot, command logs and disposable container-smoke script/results:
  `<REPOSITORY_ROOT>_codex_safety\web-sprint-20261019`.
- Synthetic viewer screenshots, real validation viewer PNGs, sampled resource
  JSON and final original-artifact integrity JSON:
  `<PRIVATE_ARTIFACT_PATH>`.
- Existing baseline diagnosis (not replaced by this sprint):
  `<PRIVATE_ARTIFACT_PATH>`.

No credentials, access tokens, private environment contents or medical image
payloads are included in this report.

## Remaining work and proposed priority

1. Review this uncommitted diff and perform an operator-controlled staging
   acceptance run with production-like PostgreSQL, model-enabled container,
   configured external checkpoint, HTTPS, real authorized case access and
   storage/backups. Review migrations explicitly before deployment; this sprint
   does not authorize applying them to an existing application DB.
2. Keep the low-quality baseline clearly experimental. Recover the missing
   training notebook, official split workbook, remaining training logs and
   additional validation CT/reference pairs before separately approved model
   experiments. No threshold/accuracy improvement is claimed by this viewer.
3. Add oblique/non-mm geometry only with dedicated correctness fixtures and
   cross-viewer comparison. Test Safari/Firefox and actual mobile/low-memory
   hardware before broad viewer rollout. Direct GPU-memory measurement remains
   unavailable; current admission is heuristic.
4. If deployment performance requires it, plan versioned/chunked volume storage
   and delivery, backend job queue/status/cancellation, and push invalidation.
   Current inference is synchronous; freshness while viewing is periodic.
5. Patient editing/deletion, password-reset email, dataset/split/model registries,
   evaluation UI, annotations, real clinical reports, centerlines/stenosis and
   calibrated uncertainty remain unavailable. These need separate backend/product
   scope rather than placeholder implementations.

## Safety confirmation

No commits, pushes, merges, pull requests, destructive resets/cleans, branch
switches, model retraining, checkpoint modifications, held-out test access or
real/existing-application-database migrations were performed. Test migrations
were confined to disposable SQLite, the temporary native PostgreSQL cluster,
and owned disposable test containers. All initial edits and model artifacts
remain preserved.

## ChatGPT coordination

Requested destination:
https://chatgpt.com/c/6ac7bbec-d72c-83ec-a0af-8d168599a543

Status: **automatic handoff blocked; no ChatGPT message sent**. The supported
Windows Computer Use tool found the running Brave window, but refused to read
its state because it could not determine the current browser URL with enough
confidence to enforce policy. Computer Use explicitly stopped for this turn.
No navigation, typing or message submission was performed, and no alternate
automation was used to bypass the restriction. The specified conversation was
not opened or reviewed by the agent. Share this complete file manually with
that conversation and use the review question below.

Requested review question:

**Please review this implementation report against the VascuAI project context
and tell me what I should do next. Identify remaining web-side implementation,
testing or deployment tasks, any problems that need fixing, and the best next
priority.**

Recommendations from that conversation are review input, not automatic
authorization to expand the sprint or modify the model/deployment.
