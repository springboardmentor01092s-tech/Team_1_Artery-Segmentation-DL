# CCTA research dataset preparation

## Scope and safety

`backend/app/services/ccta_dataset_preparation.py` and
`backend/scripts/prepare_ccta_dataset.py` provide an offline inventory and
validation boundary. They are not an API, do not modify source volumes, do not
resample data, do not write to the application database, and do not start model
training. The synthetic stenosis workflow and patient-facing clinical workflow
are unchanged. The local inventory below was limited to filenames, split-file
structure, and sample NIfTI headers; it did not inspect image or mask voxel
values or establish dataset licensing, official cohort membership, or annotation
semantics. Dataset-specific filenames, splits, licenses, annotation fields, and
label meanings must still be confirmed against the exact release documentation
before registration.

Use only de-identified dataset case and patient-group identifiers documented by
the dataset. Never enter a patient's name, MRN, accession number, date of birth,
or free-text clinical information. A dataset record is not evidence of data-use
authorization: a restricted dataset still requires the applicable external
approval, and this tool always leaves `training_eligible` false.

## Registration and standardized manifest

Input is `vascuai-dataset-registration/0.1` JSON. Each registration contains:

- `dataset`: `family` (`imagecas`, `imagecas_x`, `asoca`, or `future_ccta`),
  exact dataset `name`, `version`, source citation/URL, documented access status,
  de-identification basis, license name/status/evidence reference, and references
  to the dataset README, license, and split/annotation manifests.
- `preprocessing`: `vascuai-ccta-preprocessing/0.1`, native-orientation policy,
  explicit resampling choice, target spacing and interpolation if resampling is
  proposed, intensity/crop policies, software versions, and seed. This module
  records and hashes the configuration; it does not execute it.
- `cases`: de-identified `case_id`, de-identified `patient_group_id`, source split
  (`train`, `validation`, `test`, or `unassigned`), and relative asset paths.
  Exactly one source image/series is required per case.
- Assets are typed as `image`, `vessel_mask`, `centerline`, `mesh`,
  `lesion_annotation`, or `other_annotation`. Paths are relative, contained in
  the extracted data root, and may not traverse or use symlinks.

The output `vascuai-ccta-dataset/0.1` manifest records the relative paths,
SHA-256 and byte sizes, dimensions, native affine, spacing, coordinate frame,
axis order, geometry fingerprint, observed mask values and their documented
meanings, annotation entry counts, split/asset/missing-label summaries,
preprocessing hash, source registration, and a self-hash. `verify_manifest`
rechecks the manifest hash and re-inventories original source bytes and geometry.
Output is exclusive and refuses to overwrite an existing manifest. The CLI also
refuses registration/output documents inside the Git repository and requires its
manifest output to live outside both the repository and source dataset root.

Example preprocessing record (no resampling is performed by the inventory tool):

```json
{
  "schema_version": "vascuai-ccta-preprocessing/0.1",
  "orientation_policy": "preserve_native",
  "target_spacing": null,
  "target_spacing_units": null,
  "resampling": "none",
  "image_interpolation": null,
  "mask_interpolation": null,
  "intensity_transform": {"kind": "none"},
  "crop_policy": "none",
  "software_versions": {"preparation_tool": "0.1"},
  "seed": 42
}
```

## Supported source structures and limits

| Input | Current support | Dataset-specific step still required |
|---|---|---|
| NIfTI `.nii` / `.nii.gz` | Uses existing bounded NIfTI validation, NIfTI affine/units, nibabel axis codes, and header-only geometry. NIfTI vessel masks are scanned by z slabs to verify their discrete labels. | Confirm qform/sform choice, units, image-mask pairing and label code meanings against that release's documentation. |
| NRRD `.nrrd` | Optional `pynrrd`; preserves declared directions, origin, space, units and index order. Label maps are content-checked only within a 256 MiB estimated scan limit. | Detached `.nhdr` plus payload pairs are refused until a composite-file hashing adapter is added. Confirm axis order and space semantics from the actual header/docs. |
| DICOM CT series | Optional `pydicom`; reads metadata only, requires one flat single-frame CT series, checks consistent dimensions/orientation/pixel spacing and intensity rescale tags, orders slices by normal projection, rejects duplicate/irregular slice positions, and records LPS-mm geometry and a digest over every instance. Pixel data is not decoded. | Enhanced multi-frame DICOM, mixed series folders, DICOM SEG and DICOM RT structures need separate reviewed adapters. |
| Centerlines | Versioned JSON with source geometry fingerprint and native IJK or explicit physical coordinates; all listed points are checked against the source bounds. | Confirm source convention, branch connectivity/order and dataset-specific sidecar format before mapping. This manifest does not establish anatomical validity. |
| Lesion annotations | Versioned JSON with source geometry fingerprint, lesion center and proximal/distal boundaries, optional preserved source values/nulls and source/evidence references when values exist. Coordinates are checked against source bounds. | Inspect annotation protocol and semantics; reviewer qualification and clinical truth are not inferred. No missing value is calculated. |
| Meshes | ASCII OBJ and ASCII PLY, up to 64 MiB, with explicit coordinate frame/units and matching geometry fingerprint; vertices are checked against image bounds. | Binary PLY and VTK/VTP/STL/GIFTI are refused until individually reviewed parsers are added. |

No reorientation or resampling occurs. NIfTI uses RAS coordinates per nibabel;
DICOM uses LPS per DICOM. Geometry alignment requires matching shape, coordinate
frame, and affine within the documented numerical tolerance. When one NIfTI asset
declares spatial units as unknown, the manifest records voxel-grid/affine alignment
but explicitly leaves physical units unresolved; it never upgrades the mask to mm.
Known, conflicting units cause refusal. Raster masks
must provide an explicit value-to-meaning table including background zero, and
the observed value set must match exactly. Unsupported or missing labels cause
registration refusal rather than implicit conversion.

## Dataset-by-dataset integration sequence

The family names select a general manifest family, not a guessed folder adapter.
For each exact release, first inspect its README, license/access agreement,
official case/split manifests, image and annotation headers, and annotation
protocol. Record evidence references and a confirmed split table before writing
registration JSON. Do not infer splits from case numbers or directory ordering.

### Local dataset inventory checked for this implementation

The dataset root is represented by `<IMAGECAS_EXTRACTION_ROOT>`. Set this placeholder
to your own ImageCAS extraction directory outside the repository. Its `imagecas-raw` directory contains
an extracted segmentation-code README, a `split_1000.csv` with columns `ID,k_fold`,
an ImageCAS split workbook, and multi-part archives. The README describes prior
coronary segmentation pipelines; it is not a license or authoritative annotation
specification. No license file was present among the inspected README/split
manifest candidates, so use and redistribution terms remain unconfirmed.

The local `imagecas-split4-extracted-20261101` tree has paired
`<id>.img.nii.gz` and `<id>.label.nii.gz` assets: 700 training image/mask pairs and
50 validation pairs, with no missing or orphaned filename pairs. Header-only
samples from both splits had matching shape and affine. CT header units were
`mm`; mask units were `unknown`, so the adapter records voxel-grid/affine
alignment without inferring physical mask units. No voxel arrays were read by
this inventory check. Confirm the split workbook/count discrepancy and exact
release identity before use. The workbook sheets were not inspected because the
configured spreadsheet artifact runtime was unavailable; the CSV column
structure was inspected without emitting row identifiers.

Within the searched local datasets root, no separate ImageCAS-X v2 or ASOCA
extraction was found. Existing project evidence still treats ImageCAS-X v2
licensing as unresolved. The module can register those families only after the
exact release, license, split source, annotation protocol, and file layout have
been inspected; it does not claim those datasets are locally available.

### ImageCAS

1. Record exact release/version, source citation, license/use terms and any
   redistribution restrictions from the downloaded release itself.
2. Use the published de-identified case key as both `case_id` and
   `patient_group_id` only if the documentation confirms one scan per subject;
   otherwise record the documented subject key for grouping.
3. Map CT and any actually supplied artery annotation assets by manifest, not by
   filename guessing. Declare mask values only after checking their accompanying
   label documentation and contents.
4. Bind official train/validation/test membership. Validate that one subject does
   not occur across splits. Do not infer lesion labels from diagnosis/clinical
   metadata.

For the currently extracted local split, candidate paths use paired
`<id>.img.nii.gz` and `<id>.label.nii.gz` naming. Registration must map each pair
to `image` and `vessel_mask`, declare the observed label codes only after reviewing
annotation documentation, and bind each case to the official de-identified
patient-group ID. Directory counts alone do not establish official membership or
permission.

### ImageCAS-X

Use the same release-specific process, but do not reuse original ImageCAS
assumptions for v2 filenames, annotations, coordinate conventions, or license.
The v2 license is unresolved in the existing project evidence: record it as
`unconfirmed` with its official license evidence reference. The manifest will
keep training eligibility false. Do not use or redistribute ImageCAS-X v2 data
until its exact terms and access authorization are independently confirmed.
Centerline and lumen assets, if present, remain geometry/reference assets; they
are not expert lesion labels unless the documentation explicitly establishes
that fact.

### ASOCA

Record the exact challenge/release and official split manifest. Confirm whether
the local files are CT volumes, artery masks, or other annotations and document
their codes/units. Do not assume challenge labels encode lesion location,
severity, or percentage narrowing. Preserve the official evaluation split and
keep patient-level grouping separate from case-level file names.

### Future lesion-annotated CCTA

Require a versioned annotation schema, source-image identity, geometry
fingerprint, coordinate frame/units, lesion identifiers, native coordinates and
explicit null/unavailable reasons. Keep raw source annotations immutable. Any
human-review status, reviewer role/qualification evidence, adjudication,
measurement method and use authorization must come from independently reviewed
source documentation; this manifest cannot certify reviewers or convert
annotations into clinical ground truth.

## Commands

Run from `backend/` after preparing a registration JSON outside the repository:

```powershell
python -m scripts.prepare_ccta_dataset --root "D:\datasets\exact-release" `
  --registration "D:\dataset-prep\registration.json" `
  --output "D:\dataset-prep\manifest-unique.json"

python -m scripts.prepare_ccta_dataset --root "D:\datasets\exact-release" `
  --verify-manifest "D:\dataset-prep\manifest-unique.json"
```

NRRD requires optional `pynrrd`; DICOM requires optional `pydicom`. They are not
added to the application requirements and are not imported by application
startup. Install them only into an isolated dataset-preparation environment.
The manifest is preparation evidence, not a training authorization. A separate
review must approve dataset rights, annotation semantics, task eligibility,
patient-level splits, preprocessing and model-training protocol before any
training job is configured.
