# Case 851: saved baseline false-positive audit — 2026-10-20

Experimental research analysis, not a clinical accuracy assessment. Only the
supplied validation case 851 and its existing outputs were read. No inference,
training, postprocessing, threshold selection, held-out test access, application
changes, database operations or staging/deployment operations were performed.

## Inputs, provenance and geometry

The branch is `research/baseline-false-positive-audit`, HEAD
`428f52c1dbfe11b55bfa006c1916ac0973a7cd56`. Existing untracked `.vscode/` and
`docs/codex-handoff-to-chatgpt.md` were preserved. New repository files are:

- `research/baseline_false_positive_audit.py`
- `research/tests/test_baseline_false_positive_audit.py`
- `docs/baseline-false-positive-audit.md` (this report)

Handoff:
`F:\Documents\artery_demo\model\vascuai_model_handoff_for_codex_20261016\vascuai_model_handoff_recovered`

Saved run:
`F:\Documents\vascuai-artifacts\runs\case-851-step700-threshold070-20261016`

All eight handoff manifest checksums match. The checkpoint was **hashed only**,
never deserialized or executed. Its SHA-256 is
`e208fa586bb9bb50dc77b913caa0355a547bad529f9f0d61df17880b2efc5254`.
The CT SHA-256 matches both the handoff and saved run:
`e7cf2d52dbca642097f350aec6655c306427751a2125e28405c2e6e0a5b8dab9`.
Saved metadata records SmallUNet3D, base 8, 85,177 parameters, step 700, 64³
patches, stride 32, threshold 0.70, clip [-200,800] and `(image + 200) / 1000`.
These metadata claims were checked against the expected baseline; they do not
constitute an independent replay or a signed record of output generation.
There is no independent historical checksum manifest linking the saved probability
and prediction files to model execution. Their current hashes are now recorded.

The CT, reference, probabilities and prediction all have shape `(512,512,217)`,
56,885,248 voxels, spacing `(0.33203125,0.33203125,0.5)` and orientation `LAS`.
Their selected affines match within absolute tolerance 1e-6 (relative tolerance 0):

```text
[-0.33203125, 0,          0,   61.833984375]
[ 0,          0.33203125, 0,   79.166015625]
[ 0,          0,          0.5, 70.94999694824219]
[ 0,          0,          0,    1]
```

Each has sform code 2 and qform code 0. CT/probability/prediction spatial units
are millimetres; **reference units remain unknown**. Metrics require explicit
`--allow-reference-unknown-units`, conditional on matching shape, affine and
spacing. This assumes voxelwise correspondence; matching headers alone cannot
prove anatomical registration or annotation completeness. No header was edited,
no image was reoriented or resampled, and no physical-volume metrics are reported.

CT is stored as int16, reference as float64, probabilities as float32 and saved
prediction as uint8, with identity data scaling. Reference labels are evaluated
as `label > 0` in their original precision before conversion to boolean. All
read voxel values are finite; probability values are bounded in [0,1]. The saved
prediction is binary and equals `probability >= 0.70` at **every voxel**.
Original saved counts and Dice were reproduced. All 13 tracked input files,
including both manifests and all four saved-run files, have identical SHA-256
before and after analysis; the individual hashes are in `audit.json`.

## Measured threshold sensitivity

All 56,885,248 voxels are evaluated; reference foreground is 117,888. Predictions
use `probability >= threshold` with the stored float32 values, without rounding.
These four thresholds are descriptive comparisons, **not a threshold search or
selection**. Zero-denominator metrics are JSON null / blank CSV fields and named
in `undefined_metrics`; none of these whole-volume case metrics are undefined.

| Threshold | TP | FP | FN | TN | Dice | IoU | Precision | Recall |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0.50 | 61,487 | 710,909 | 56,401 | 56,056,451 | 0.138129 | 0.074188 | 0.079606 | 0.521571 |
| 0.60 | 51,828 | 604,405 | 66,060 | 56,162,955 | 0.133902 | 0.071755 | 0.078978 | 0.439638 |
| 0.70 | 45,191 | 522,703 | 72,697 | 56,244,657 | 0.131794 | 0.070546 | 0.079576 | 0.383338 |
| 0.80 | 38,562 | 443,710 | 79,326 | 56,323,650 | 0.128506 | 0.068665 | 0.079959 | 0.327107 |

At 0.70, 567,894 voxels are predicted foreground: approximately 4.817 times the
reference foreground. About 92.04% of predicted foreground is outside the
reference. Raising the threshold from 0.70 to 0.80 removes both FP and TP while
precision stays around 8%. This does not support treating a small threshold
adjustment as sufficient to resolve this case's false-positive problem.

## Measured connected components at 0.70

Connectivity is **6-connected in the stored 3D array**: face-sharing neighbors
along one axis only, with no edge/corner adjacency and no array-boundary wrapping.
The algorithm uses sparse foreground indices rather than a full 3D integer label
image. Component IDs are deterministic from the first C-order foreground index;
CSV rows are sorted by decreasing size. No components or voxels were removed.
Connectivity uses topology, not millimetre distance; anisotropic spacing and a
different adjacency definition can change the component counts.

There are **477 components**. Sizes range from 1 to 26,257 voxels; mean 1,190.55,
median 245, 25th percentile 31, 75th percentile 1,004, 90th percentile 2,812.8,
95th percentile 5,031.8 and 99th percentile 16,467.16 (NumPy linear quantiles).

| Component size | Components | Predicted voxels | TP | FP |
| --- | ---: | ---: | ---: | ---: |
| 1 | 31 | 31 | 1 | 30 |
| 2–9 | 42 | 179 | 13 | 166 |
| 10–99 | 109 | 4,395 | 233 | 4,162 |
| 100–999 | 175 | 74,994 | 3,722 | 71,272 |
| 1,000–9,999 | 109 | 308,806 | 41,222 | 267,584 |
| ≥10,000 | 11 | 179,489 | 0 | 179,489 |

| Reference-overlap category | Components | Predicted voxels | TP | FP |
| --- | ---: | ---: | ---: | ---: |
| Zero overlap | 439 | 518,438 | 0 | 518,438 |
| Mixed correct/incorrect voxels | 26 | 48,896 | 44,631 | 4,265 |
| Entirely within reference | 12 | 560 | 560 | 0 |

Zero-overlap components account for **99.184% of all FP voxels**. The largest
component (ID 387) has 26,257 voxels, **4.6236% of predicted foreground**, all FP
relative to this reference. All eleven components of at least 10,000 voxels have
zero reference overlap. In contrast, components smaller than 100 voxels contribute
only 4,358 FP voxels (about 0.834% of all FP). Thus most FP burden consists of
separate, sizeable regions rather than a few tiny speckles or only boundary
leakage from reference-overlapping components.

These are overlap categories, not anatomical diagnoses. An unannotated structure
can have zero overlap without being proven non-arterial. An automatic
"keep-largest-component" rule would retain a zero-TP component on this case.
Reference-dependent removal of zero-overlap components would use ground truth
and must not be presented as a deployable postprocessing method.

## Probability and intensity measurements

The histogram has 50 equal-width probability bins over [0,1], with separate
counts for reference foreground/background. Bins are left-closed/right-open
except the final bin includes 1. Histograms, not voxel tables, are exported.
Scores are **uncalibrated model outputs**, not clinical confidence.

- Reference foreground score median: 0.51754; mean: 0.53031.
- Reference background score median: 0.03293; 99th percentile: 0.64430. The
  distribution has a low-score bulk and a substantial high-score tail.
- TP at 0.70: score median 0.92944, mean 0.90305.
- FP at 0.70: score median 0.93297, mean 0.90529.
- FN at 0.70: score median 0.28253, mean 0.29859.

The FP score distribution at 0.70 is not simply concentrated near the decision
boundary. Every one of the 217 slices along array axis 2 has FP; the largest
slice count is 5,743 FP at index 173. This axis is reported as stored array k,
not an independently reoriented/resliced image.

Stored/scaled CT intensity medians are 189 for TP, 135 for FP and 84 for FN.
Of 522,703 FP voxels, 69,830 are below -200 and 4,530 above 800, whereas no TP
voxels lie outside these clipping bounds. Most FP voxels nevertheless lie
inside the clipping range. These counts describe intensities before clipping;
the current task did not recalculate inference or validate scanner HU calibration.
Intensity alone cannot identify the anatomical structures being segmented.

## Interpretation: hypotheses and proposed next experiments

**Measured:** the saved mask/threshold, source hash and numerical geometry agree;
no inconsistency was found that would explain FP as a stale mask or threshold
application error. This does not independently prove semantic image alignment.
Error burden is dominated by sizeable zero-overlap regions with high model scores,
not just tiny islands or near-threshold boundary voxels.

**Hypotheses, not established causes:** the model may respond to structures or
context outside the annotation target, may have inadequate negative-example
coverage, or may reflect training objective/sampling/domain limitations. Reference
scope/completeness and actual anatomical registration also need confirmation.
This audit does not attribute a cause to loss weighting, sampling or training
implementation: those are not measured by these saved outputs.

Proposed next work, requiring separate approval/data as applicable:

1. Inspect the highest-FP components against CT/reference in a trusted imaging
   tool with an appropriate reviewer. Confirm image identity, registration,
   annotation scope and why the reference has unknown spatial units.
2. Recover training notebook/source, exact split workbook, sampler coordinates,
   loss definition/weights, preprocessing/orientation configuration, and complete
   logs/validation reports. Compare actual code with checkpoint-compatible input
   processing; do not infer missing training behavior from this single case.
3. Repeat this frozen diagnostic on several additional **validation** cases with
   independently verified geometry and provenance. Keep held-out test data sealed.
4. Only then predefine and evaluate candidate threshold/calibration, sampling,
   loss/context or anatomy-informed postprocessing experiments on validation
   data. Do not select a final threshold or connected-component rule from 851.

## Reproduction, environment and outputs

From `F:\Documents\artery_demo`, use the existing backend virtual environment:

```powershell
.\backend\.venv\Scripts\python.exe -m pytest research/tests/test_baseline_false_positive_audit.py -q

.\backend\.venv\Scripts\python.exe research/baseline_false_positive_audit.py `
  --handoff-dir 'F:\Documents\artery_demo\model\vascuai_model_handoff_for_codex_20261016\vascuai_model_handoff_recovered' `
  --run-dir 'F:\Documents\vascuai-artifacts\runs\case-851-step700-threshold070-20261016' `
  --output-dir 'F:\Documents\vascuai-artifacts\diagnostics\case-851-baseline-audit-20261020' `
  --allow-reference-unknown-units
```

The recorded output directory now exists. **For a repeat run choose a new output
directory outside the repository**; the script refuses existing directories and
does not overwrite reports. It rejects geometry/provenance/content failures
before writing reports. It rehashes inputs after analysis and refuses success if
any original input hash changed. It reads only explicitly named case-851 volumes
and handoff manifest entries; it does not search for other dataset cases.

Execution environment: Windows 11 (10.0.26200), Python 3.14.7,
NumPy 2.5.4, NiBabel 5.4.2, Pytest 9.1.1. No dependencies were installed.
The existing external `baseline-step700-20261017/diagnose.py` was inspected for
prior assumptions but **not executed** because it includes model loading/inference.
The new script imports no model or application pipeline. SciPy and Matplotlib
were unavailable; sparse component traversal uses Python/NumPy and the histogram
is exported as binned CSV counts. No optional image plot was generated.

Synthetic tests: **36 passed, 0 failed, 0 skipped**. They cover hand-computed
confusion values and undefined denominators, positive-label semantics including
tiny float64 positives, inclusive float32 thresholds, binary prediction equality,
invalid probabilities/data, signed-affine geometry, unknown-unit opt-in and hard
geometry/metadata mismatches, component TP/FP totals, empty components, diagonal
separation and row/plane wrapping, histogram endpoints, provenance failures and
output overwrite/repository-write prevention. No backend database fixtures ran.

Reports are in:
`F:\Documents\vascuai-artifacts\diagnostics\case-851-baseline-audit-20261020`

- `audit.json`: geometry, measurements, distributions, environment and before/after
  input SHA-256 values; includes the exact executed diagnostic script's SHA-256.
- `threshold-metrics.csv`: four whole-volume threshold comparisons.
- `components-070.csv`: 477 component rows with size, TP, FP and overlap category.
- `component-size-distribution.csv`: six size bins with overlap totals.
- `probability-histogram.csv`: 50 bins, reference foreground/background counts.
- `slice-counts-070.csv`: 217 axis-2 slice summaries.
- `findings.md`: a copy of this report beside the numeric outputs.

No voxel-level CSV, mesh, model weights, medical volume copy, or derived prediction
was created. No application/frontend/backend implementation, API, schema,
inference code or staging configuration was changed. No branch switch, staging,
commit, push, merge, reset or repository cleanup was performed.
