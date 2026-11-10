# Frontend segmentation workflow

This guide describes the authenticated current workspace. The CT/mask viewer,
geometry restrictions and rendering limitations are documented in the
[viewer guide](frontend-segmentation-viewer.md). No model-performance or clinical
claim follows from successful rendering.

## Existing integration points

The existing protected `/cases/:id/analysis` route uses `AnalysisResult.jsx`.
`/cases/:id/analysis/:analysisId` remains supported and highlights a matching run
from server history, or explains that the requested run is absent. `CaseDetail`
provides the shared case tabs and now links to the Segmentation workspace from
the overview and study-history pages. Navigation, the AppShell, palette, shared
cards and mobile layout are preserved.

The existing Axios client provides the configured `VITE_API_URL` (default
`/api/v1`), bearer token interception and current-session 401 handling. No second
HTTP client is introduced. Existing `useCase`, `useRemote`, `useAuth`, and
`CLINICAL_WRITERS` permissions are reused. Segmentation history stays separate
from `CaseResponse`: its legacy `analyses` array is not populated with fabricated
or unrelated results.

## User-visible workflow

1. Open a case, then its **Segmentation** tab.
2. Inspect input eligibility. A stored NIfTI volume, recorded `CTA` or
   `CT Angiography` modality, and metadata declaring exactly 3 dimensions are
   required. A 2D image, absent metadata, failed metadata fetch, incompatible
   modality or 4D volume cannot enable Run. Links lead to input metadata and the
   existing case/upload screen. Case and input checks can be refreshed.
3. Clinician and Admin users can choose a finite threshold in **[0,1]**, default
   **0.70**, then choose **Run segmentation**. Researcher and DataScientist users
   see read/download guidance and no run action.
4. The UI sends `POST /cases/{id}/segmentations` with `{ "threshold": value }`
   through the authenticated client. The synchronous request uses no invented
   progress percentage. Controls show “Segmentation running…” and remain disabled
   while the page's request is active. A ref guards immediate repeated events;
   the shared adapter also rejects a second request for the same case while its
   previous request is pending, including after a page remount.
5. HTTP **201** is required before showing that persistence succeeded. The UI
   then reloads `GET /cases/{id}/segmentations`; it does not insert the POST
   response as a locally fabricated history item. If history refresh fails,
   the saved-run confirmation and actual history error remain distinct.
6. History shows backend creation times, authoritative current/stale flags,
   threshold, architecture, checkpoint step, dimensions, patch/stride, runtime,
   source checksum and checkpoint checksum. Missing values are “Not recorded”.
   Metadata rendering is an allowlist; internal storage paths and unsupported
   clinical output fields are not displayed.
7. Current results expose **Download mask** and **Download probabilities**.
   Stale results explain why downloads are blocked and disable both actions.
   A fresh backend 409 during download triggers a history refresh.

Loading, empty, failure and inaccessible states are explicit. Server-provided
messages are preserved; 409 explains that inputs/history should be refreshed,
503 distinguishes a busy worker from administrator configuration work, and 403
explains access restrictions. Network/500 failures explain that server processing
may still finish and history should be refreshed before retrying. There is no
backend job-status, polling or cancellation API, so navigating away does not
claim to cancel inference. Session expiry follows the existing login redirect.

## API contract and download security

No backend/schema/migration changes were made. The frontend uses the existing:

- `POST /api/v1/cases/{id}/segmentations` — Clinician/Admin, JSON request, 201 after persistence.
- `GET /api/v1/cases/{id}/segmentations` — all four case-reader roles.
- `GET /api/v1/cases/{id}/segmentations/{result_id}/mask` — authenticated binary NIfTI download.
- `GET /api/v1/cases/{id}/segmentations/{result_id}/probabilities` — authenticated float32 NIfTI download.

The response fields inspected were `id`, `case_id`, `created_at`, `stale`,
`metadata`, `mask_url` and `probabilities_url`. Downloads construct the known
relative route from case/result IDs and artifact kind, preserving the configured
API base. They do not follow returned URLs with bearer credentials: this avoids
cross-origin token disclosure and accidentally duplicating `/api/v1`.

Downloads request a Blob through the same Axios instance, so the bearer token is
sent. HTTP errors are handled before saving; Blob-wrapped JSON details are decoded
for the error UI. Empty bodies, unexpected status, JSON/HTML/text responses and
invalid artifact IDs are rejected. Successful files use temporary object URLs,
which are revoked, with names:

```text
case-{id}-segmentation-{resultId}-mask.nii.gz
case-{id}-segmentation-{resultId}-probabilities.nii.gz
```

If the component unmounts or the session token changes before a download finishes,
the old response is not handed to the browser. No public static storage mount or
internal filesystem path is introduced.

## Verification

From frontend-react, use `npm test`, `npm run build`, `npm run lint` and, after
setting up the supported Playwright browser, `npm run test:e2e`. A custom browser
path is optional machine-local configuration, not a repository default.

Contract/browser fixtures exercise roles, thresholds, authoritative history,
duplicates, failures, protected downloads, stale responses and accessibility.
Mocked browser tests do not verify real inference or an application database.
No private screenshot/evidence directory is required and no historical run count
is asserted as a fresh result for this submission.

## Limits and remaining contract gaps

- The model is an experimental research baseline, not clinically validated.
  No stenosis, severity, confidence, clinical findings or Dice scores are invented.
- The current [viewer](frontend-segmentation-viewer.md) shows protected CT/mask
  slices and binary 3D rendering, subject to its geometry/resource admission rules.
- The history API does not expose model readiness or worker progress. Actual
  input/model availability is established by the run request and its response.
- Synchronous inference inherits server/proxy timeouts. There is no durable job
  queue, completion notification, cross-tab request coordination or cancellation.
  A lost response can leave processing active; inspect refreshed history before
  retrying. Page reload clears the adapter's pending-request guard.
- Downloads buffer the volume as a browser Blob, so very large outputs require
  corresponding browser memory. No alternate public download path was added.
- A real browser-to-model run requires separately authorized data and configuration;
  source/contract tests do not establish medical performance. Genuine quantitative
  stenosis remains unavailable. Fixtures and empty states never become real results.

Key implementation paths are `frontend-react/src/pages/AnalysisResult.jsx`,
`src/api/segmentation-contract.js` and `src/lib/segmentation.js`. Data, weights,
generated outputs, screenshots and environment files are excluded from the review
snapshot.
