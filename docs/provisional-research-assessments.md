# Provisional mask-profile assessments

This is local, algorithm-assisted research software, not a stenosis model, expert
annotation service or clinical review. Both release authorizations remain false.
It preserves the separate human R1/R2/submission/adjudication system unchanged.

## What runs

The existing offline `experimental_candidates.extract_candidates` samples a supplied
binary mask along explicitly ordered, source-bound centerlines. It refuses missing
support, ambiguous components, pockets, field-of-view and geometry failures. It does
not obtain reliable arbitrary centerlines automatically. No existing refusal or
resource cap has been relaxed. The original CT and mask are never modified.

In the CT + predicted segmentation viewer, expand **Experimental local candidate
preview** and load the existing `experimental-candidates/1.0` output for that exact
saved model run. Existing validation recomputes candidate support, coordinates and
the canonical categorical mask hash. Reference annotations are refused as predictions.
The new workbench additionally rehashes the actual displayed mask labels each time.

Choose **Run provisional research assessments**:

1. R1 uses linearly interpolated bidirectional median reference areas.
2. R2 separately uses the smaller of the two directional mean reference areas.
3. Each uses the supplied profile's original area-ratio trigger and minimum contiguous
   support, without tuning. R3 compares frozen section decisions and retains every
   proposal from both procedures. Disagreements stay unresolved. No majority label
   or agreement-as-ground-truth is generated.

These are deterministic procedures, **not three AI models, LLM calls or human
reviewers**. The AI assistance comes only from a model-derived artery mask when an
actual prediction is supplied. Shared mask/profile/sampling errors mean the two
procedures are not statistically independent. The synthetic tests do not execute
a segmentation model or establish real lesion-detection performance.

## Proposals and measurements

Each proposal retains native IJK/RAS center coordinates, first/last triggering sample
bounds, branch support, reference method and source hashes. Branch order is not
assumed to establish anatomical proximal/distal direction. Artery identity, severity,
confidence and uncertainty remain null/unavailable; no artery classifier exists.

The diagnostic profile diameter is `2*sqrt(area/pi)`. Its diagnostic reduction is
`100*(1-sqrt(area/reference_area))`. This is an unvalidated comparison of equivalent
diameters, not a clinical caliper measurement, stenosis ground truth or gate approval.

Optional **unverified caliper arithmetic** accepts four native IJK endpoints and a
description of plane/reference selection. Affine Euclidean distances produce
`100*(1-D_min/D_reference)` only with complete, finite, in-bounds endpoints, positive
lengths, reference >= minimum and explicit method evidence. Partial inputs remain
unavailable. Zero reduction is retained when both positive diameters are equal.
Inverted references are unassessable; values are not clamped. The software cannot
verify that a plane, lesion or reference is anatomically appropriate.

## Provenance, export and separation

The standalone `simulated-research-assessment/0.1` JSON includes the source CT file
hash, canonical mask-array hash (not a mask-file checksum), geometry/branch/parameter
fingerprints, saved segmentation identity and available model metadata. Missing model
name/version/recipe/checkpoint/threshold remain null. Hashes bind supplied evidence;
they do not attest that an algorithm was executed by a trusted server.

R1/R2 snapshots are frozen in memory and R3 hash-links both. Standalone restore and
export recompute all procedures, arithmetic, hashes and current-source bindings.
Altered flags, records, sources or metadata are rejected before creating a download.
Session/source changes invalidate pending work. Normal clinical/report JSON exports
refuse these documents, including nested/stripped research measurement objects.

There is **no authenticated immutable AI submission/history service**. Download each
snapshot separately to retain it; local files are editable and checksums are
tamper-evident only when checked against the current source. Nothing is saved to
the database, human-review routes, evaluation metrics, training datasets or analytics.
Assigned blinded accounts remain restricted by existing server guards and cannot
retrieve these segmentation inputs. This work does not seed reviewer credentials.

## Limits and unavailable AI

The viewer still refuses unsupported oblique/sheared geometry and retains its
existing display budget; local profile masks remain limited to 4 million voxels and
documents to 2 MiB. Typical full-size CT/masks exceed this experimental path. There
is no newly validated full-volume automatic centerline/candidate service. Do not crop
or relabel a source silently to bypass these controls.

Available ImageCAS/ImageCAS-X lumen masks and centerlines do not establish lesion
positions, lesion boundaries, clinical diameter/severity labels or independent expert
reviews. Restricted datasets have not been accessed or converted to training labels.
No stenosis classifier is trained and Validation is not repurposed for training.

Grad-CAM requires gradients of an actual model target. It could be investigated for
an actual segmentation target but must be labelled segmentation attribution, with
its own reproducible forward/backward protocol. There is no stenosis prediction
target here, so no stenosis Grad-CAM or surrogate heatmap is generated. Profile
trigger support is a geometric explanation, not model attribution. See the
[original Grad-CAM paper](https://arxiv.org/abs/1610.02391).

## Verification

Node tests exercise the public creation/restore/export functions against real
serialized outputs of the synthetic backend extractor. A deliberately asymmetric
reference fixture produces a true R1/R2 procedural disagreement, independently
regenerated by Python. Browser tests exercise the actual viewer UI, local downloads,
restore rejection, arithmetic, print hiding and delayed-session refusals using
synthetic CT and intercepted APIs. These are not clinical accuracy measurements.

## Bounded native-volume offline workflow

The separate `backend/scripts/research_candidate_profile.py` path now verifies the
original CT/mask file hashes and exact coded native geometry, expands a compressed
uint8 mask into a new bounded snapshot, scans the entire categorical mask in slabs,
and maintains six-connected components using a compact previous-slice frontier.
Only requested planes/centerline samples are gathered from the mapped mask. The
existing plane/reference calculation is shared with the original small-array path;
golden outputs match without changing research thresholds, sample pitch or rules.

Limits: 134,217,728 native voxels; 1,048,576 pixels per I/J slice; 65,536 active/local
component labels; 262,144 hash values per slab; compressed/source files at most
2 GiB; expanded uint8 mask at most 130 MiB. Existing branch/plane/section limits
remain unchanged. Exceeding any limit is an explicit refusal. Every voxel contributes
to the canonical identity and connectivity scan; no crop, downsample, label removal,
smoothing, nearest-component selection or disconnected-component discard occurs.
These are allocation/storage budgets, not a kernel-enforced process-memory guarantee.

This accepts supplied ordered branches, not automatic skeleton extraction. Empty or
disconnected sources abstain. Complex frontiers refuse. Unknown mask units, scaling,
non-uint8 masks, shear, mismatched/rounded planned affine, uncoded CT geometry and
source changes refuse. Orthogonal oblique and anisotropic sampling are supported
offline. Numeric CT/mask grid agreement is not anatomical registration. Actual
ImageCAS reference-mask units remain unresolved; this tool does not silently assign
them millimetres. Original files remain untouched.

The plan's Training/synthetic declaration is an operator declaration, not an
authoritative split/licence attestation. Independently verify an actual Training
source against the dataset manifest before using it. Testing and Validation plans
are refused by this research tool. ImageCAS CT attribution and CC BY-NC 4.0
non-commercial restrictions remain applicable; ImageCAS-X annotation licensing does
not relicense the CT. No dataset is distributed or downloaded by these scripts.

Outputs include full source-bound section/candidate evidence, file/parameter/branch
hashes, implementation hashes, dependency versions and both release flags false.
Directory/file creation is exclusive. Collisions never overwrite. Failed runs retain
partial evidence and do not publish success. The output parent must be private for
real data: POSIX modes alone are not proof of Windows ACL protection.

### Reproduce the executed synthetic demonstration

From the review checkout, use an environment with the existing backend/Pydantic,
NumPy, SciPy and NiBabel dependencies. No model checkpoint or database is needed:

```powershell
$Demo = Join-Path $env:TEMP ('vascuai-synthetic-profile-' + [guid]::NewGuid().ToString('N'))
python -B backend/scripts/demo_research_profile.py --output $Demo
python -B backend/scripts/research_candidate_profile.py `
  --ct "$Demo/synthetic-ct.nii.gz" --mask "$Demo/synthetic-mask.nii.gz" `
  --plan "$Demo/plan.json" --output "$Demo/replay"
(Get-FileHash "$Demo/profile-run/profile.json").Hash -eq (Get-FileHash "$Demo/replay/profile.json").Hash
```

The generated 129×129×257 anisotropic fixture has 4,276,737 native voxels. It is
explicitly synthetic, not an original patient CT, actual model prediction, clinical
lesion or training label. The repeated profile hashes match. Successful runs delete
only their own newly created decompressed snapshot; source inputs and reports remain.

The browser still enforces its original 4-million-mask-voxel research-preview limit
and oblique-viewer refusal. The full-volume offline wrapper is not an attested
browser import. Use the emitted original IJK/RAS coordinates in a verified desktop
viewer with the original CT/mask, respecting its coordinate convention. Do not relabel
the supplied synthetic mask as a saved AI prediction to bypass viewer validation.

To exercise the separate browser workflow with clearly synthetic, test-only inputs:

```powershell
cd frontend-react
npx playwright test tests/e2e/research-assessment.spec.js --headed --workers=1
```

This browser test uses intercepted APIs. Actual HTTP/PostgreSQL reviewer-isolation
tests are separate and do not constitute a stenosis-model demonstration.

## Visual calculation evidence

After running the local assessments, expand **Calculation evidence: profiles, support
and disagreements**. The SVG and accessible table show the exact sampled mask area,
R1/R2 reference areas and trigger areas, unavailable gaps, selected left/right support
windows, section refusals, raw trigger decisions, accepted contiguous-region IDs and
unresolved disagreements. Selecting a sample revalidates the source-bound snapshot
before locating its native position in the CT. Raw triggers that fail minimum region
support are not presented as accepted regions. Green/orange bands are geometric
support/disagreement evidence, not Grad-CAM, confidence or an anatomical lesion map.

The caliper worksheet now shows its formula, original endpoints, units and assumptions.
Shear and conflicting unit declarations refuse; supported oblique arithmetic does
not enable oblique browser rendering. Clinical interpretation remains unavailable.
