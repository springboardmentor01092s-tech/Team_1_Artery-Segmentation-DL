# ImageCAS local extraction audit

**Audit date:** 2026-11-25
**Status:** Read-only audit complete for the extracted Fold 4 Training and Validation files. Dataset use/redistribution authorization remains unconfirmed; no model training was performed or authorized by this audit.

## Scope and method

Inspected the local extraction `imagecas-split4-extracted-20261101` and the locally available ImageCAS split workbook and segmentation-code package. Only the extracted `Training` and `Val` NIfTI pairs were decoded. The `imagecas-raw` multipart archive payloads and the 250 held-out Fold 4 Testing cases were not opened or extracted. Source CT and mask files were not written, copied, resampled, or otherwise changed.

All 750 extracted image/mask pairs were loaded through NiBabel 5.4.2 / NumPy 2.5.4, Python 3.14.7. For every pair, the scan checked complete payload readability, three-dimensional shape, finite CT and mask values, integer-valued mask labels, dimensions, affine equality (absolute tolerance `1e-5`, relative tolerance `1e-7`), orientation codes, voxel spacing and declared spatial units. Mask label frequencies and foreground counts were accumulated per slice/per volume. An additional streaming SHA-256 pass checked exact compressed-file duplicates separately within image and mask types. The scan processed one pair at a time; no 3D arrays were retained across cases.

## Local structure and file reconciliation

The extraction contains **1,500 files total**: 700 Training CTs + 700 Training masks, and 50 Validation CTs + 50 Validation masks. Every file is `.nii.gz`, named `<dataset-id>.img.nii.gz` or `<dataset-id>.label.nii.gz`.

| Folder | CT files | Mask files | Pairs | Notes |
|---|---:|---:|---:|---|
| `Training/201-400` | 150 | 150 | 150 | Range-style folder name is not used to assign splits. |
| `Training/401-600` | 200 | 200 | 200 | |
| `Training/601-800` | 200 | 200 | 200 | |
| `Training/801-1000` | 150 | 150 | 150 | |
| `Val/801-1000` | 50 | 50 | 50 | |
| **Total** | **750** | **750** | **750** | No `Testing` directory in this extracted tree. |

Pairing used the exact numeric filename stem plus `.img`/`.label`, not directory ordering. There are **0 missing/orphan pair members**, **0 duplicate case IDs within/across extracted splits**, **0 unexpected files**, and **0 exact-byte duplicate image files or mask files**. This is an inventory of the extracted tree only; the uninspected multipart archive contents are outside this finding.

### Split workbook reconciliation

The local `imageCAS_data_split.xlsx` has sheets `v1` and `v2-latest`; the header is on row 2, with 1,000 case rows per sheet. In each sheet, every Fold 1–4 column contains 700 `Training`, 50 `Val`, and 250 `Testing` entries. The extracted numeric IDs exactly match the `v2-latest` Fold 4 membership sets:

| Fold 4 group | Workbook cases | Extracted cases | Match |
|---|---:|---:|---|
| Training | 700 | 700 | Exact ID-set match; 0 missing, 0 extra |
| Val | 50 | 50 | Exact ID-set match; 0 missing, 0 extra |
| Testing | 250 | 0 | Not present in extracted tree; not inspected |

Thus the earlier 700/50 versus 1,000 discrepancy is reconciled for the extracted tree: it is the official workbook’s Fold 4 Training + Val subset, not a full 1,000-case extraction. Do not treat the absent 250 Testing cases as missing Training/Val files or assign them elsewhere.

The separate `split_1000.csv` in the checked-out segmentation-code package has 1,000 rows with a legacy `ID` column and `k_fold` counts of 250 for folds 1–4. Its accompanying utility code forms a cross-validation split by using one `k_fold` group as validation and the other three as training. These IDs do not match the workbook’s `v2-latest` IDs and no crosswalk was found. It is a separate CV scheme, not a source for relabeling the extracted official Fold 4 membership. The workbook’s `v1` sheet has the same split counts but a different `FileName` identifier space; no case-level crosswalk to the numeric extracted IDs was found, so that sheet was not used for the reconciliation.

## Full-volume image and mask findings

### Readability, alignment and geometry

| Measure | Training (n=700) | Val (n=50) |
|---|---:|---:|
| Image and mask decode errors | 0 | 0 |
| Non-finite CT voxels | 0 | 0 |
| Non-finite or non-integer mask voxels | 0 | 0 |
| Shape/affine mismatches | 0 | 0 |
| Empty masks | 0 | 0 |
| CT declared spatial units | `mm` (700/700) | `mm` (50/50) |
| Mask declared spatial units | `unknown` (700/700) | `unknown` (50/50) |
| NiBabel axis codes | `LAS` (700/700) | `LAS` (50/50) |
| In-plane spacing range, I/J axes | 0.2890625–0.46484375 mm | 0.318359375–0.423828125 mm |
| Median I/J spacing | 0.349609375 / 0.349609375 mm | 0.3564453125 / 0.3564453125 mm |
| K-axis spacing | 0.5 mm (700/700) | 0.5 mm (50/50) |
| Dimensions | 512 × 512 × 166–277 | 512 × 512 × 206–275 |
| Median K dimension | 275 | 275 |

The image and mask affines match pairwise and their shapes match, so the voxel grids are aligned numerically. The CT headers declare millimeters, but mask headers declare unknown units. Therefore this audit verifies voxel-grid/affine alignment only; it does **not** assert physical-unit equivalence for the masks or report physical mask volume in mm³. LAS axis codes describe the NIfTI voxel-axis directions; they are not an instruction to reorient the source. No reorientation was performed.

The published ImageCAS paper reports 512 × 512 × 206–275 image dimensions. Four Training volumes fall outside that reported K range: dataset IDs **303** (187 slices), **726** (166), **750** (277), and **848** (200). They fully decoded and their corresponding masks matched shape and affine. They are flagged for release/preprocessing provenance review, not called corrupt. No Val volume was outside the reported range.

### CT intensity summary

Values are the values returned by NiBabel’s NIfTI data proxy. They are not independently calibrated or labeled as HU by this audit.

| Split | Min | Max | Mean across decoded voxels |
|---|---:|---:|---:|
| Training | -1,024 | 3,071 | -187.3274 |
| Val | -1,024 | 3,071 | -175.3212 |

### Actual mask voxel values and foreground counts

Across all 750 masks, the only observed values were **0** and **1**: `0` = 50,435,568,477 voxels, `1` = 83,250,339 voxels. The official ImageCAS documentation describes the task as coronary-artery segmentation; the binary foreground is therefore reported as the coronary-artery segmentation foreground, not as an inferred lesion or stenosis class. No unexpected labels were observed.

| Split | Foreground voxels total | Per-mask min / median / mean / max | Mean per-case foreground fraction | Per-case range |
|---|---:|---:|---:|---:|
| Training | 77,719,083 | 35,650 / 108,198.5 / 111,027.26 / 227,301 | 0.1670% | 0.04945%–0.39316% |
| Val | 5,531,256 | 44,465 / 108,005.5 / 110,625.12 / 212,753 | 0.1611% | 0.06168%–0.29512% |

Foreground statistics are voxel counts and fractions. Because mask spatial units are unknown, no mm³ volume is calculated. Each mask had nonzero foreground.

## Annotation semantics and limitations

The original ImageCAS paper and its official project repository describe a **coronary artery segmentation** dataset. The paper’s figure caption says coronary subclasses are not further individually labeled. The paper also states that true centerline labels were unavailable for its centerline-based benchmark methods; the benchmark skeletonized pre-segmented labels to form approximate centerlines. The local extracted tree contains no centerline sidecars, meshes, branch-specific label maps, lesion tables, lesion boundaries, minimum/reference lumen diameters, percentage narrowing, or lesion severity annotations.

The local masks are binary at the voxel level. The official dataset task is coronary-artery segmentation; the local artifact alone does not establish a distinct, adjudicated lumen-vs-wall semantic protocol. In particular, a binary artery mask does not identify lesion sites or encode stenosis degree. Dataset-level disease/CAD descriptors, if obtained separately, must not be converted into lesion labels.

Accordingly, the local extraction can support a **coronary artery segmentation** task only after rights, split provenance, mask semantics and preprocessing are reviewed. It does **not** supply lesion-level supervision for a stenosis detector, severity classifier or percentage-narrowing model. No such labels were generated here.

## Dataset version, access and licensing

The local workbook includes a sheet named `v2-latest`, and its Fold 4 case IDs reconcile exactly with the extracted Training/Val IDs. This supports identifying the split table used; it does not prove the precise image release/build or archive provenance. The official ImageCAS project README describes approximately 1,000 CTAs and an official split, notes duplicate-case folder issues in older downloads, and says to contact the author for a dataset/benchmark download link and password. No license or data-use grant was found in the inspected local README, workbook or code package, nor on the inspected project README. Thus **license, reuse and redistribution permission remain unconfirmed**. Do not publish or redistribute these files, or treat local availability as authorization.

## Dataset-preparation module exercise

The registration/manifest path was **not run on this dataset**: its access/license evidence is insufficient to prepare a provenance-asserting data manifest. The module’s behavior was tested using isolated synthetic NIfTI, fake NRRD/DICOM header adapters, path/split/geometry/label errors, and manifest verification. The generated manifest always leaves `training_eligible=false`. The current audit itself performed read-only header/payload validation and did not create a dataset manifest or alter any source file.

## Readiness and required actions

- **Segmentation dataset structure:** locally paired and voxel-readable for 700 Training + 50 Val cases; numerical grid alignment verified. Mask physical units remain unknown.
- **Training readiness:** **BLOCKED** pending documented dataset-use authorization, exact archive/release provenance, resolution of the four Training slice-count outliers, and review of the intended mask semantics/preprocessing.
- **Stenosis supervision:** **NOT AVAILABLE** in this extracted ImageCAS subset. Obtain a separately authorized lesion-annotated CCTA source with lesion locations/boundaries and reviewed measurement labels, or have a qualified clinical team generate and independently review annotations under an approved protocol. Disease-level metadata and artery masks are not substitutes.
- **Testing split:** 250 Fold 4 Testing entries are identified by the workbook but are absent from this extraction and were not inspected or used.
- **No model training** was run as part of this audit.

Before any future registration: preserve the official Fold 4 assignments directly from workbook sheet `v2-latest`; use documented de-identified IDs and patient-group IDs; map `.img.nii.gz` to `image` and `.label.nii.gz` to `vessel_mask`; declare only the observed 0/1 meanings confirmed by the official label documentation; record license and release evidence; retain native orientation; and keep mask units unresolved unless the release documentation establishes them. Do not use the split helper to reassign official cases. Training requires a separate approval after all blockers are resolved.

## Reproducible inspection commands

Run in PowerShell with the dataset root kept outside Git. These commands are read-only; the full voxel scan is intentionally sequential and may take tens of minutes.

```powershell
$DataRoot = 'F:\path\to\vascuai-artifacts\datasets\imagecas-split4-extracted-20261101'
$Workbook = 'F:\path\to\vascuai-artifacts\datasets\imagecas-raw\outer-extracted\imageCAS_data_split.xlsx'
Get-ChildItem -LiteralPath $DataRoot -File -Recurse | Group-Object Extension | Select-Object Name,Count
Get-ChildItem -LiteralPath "$DataRoot\Training" -File -Recurse -Filter '*.nii.gz' | Measure-Object
Get-ChildItem -LiteralPath "$DataRoot\Val" -File -Recurse -Filter '*.nii.gz' | Measure-Object
Push-Location backend
python -m pytest --noconftest tests/test_ccta_dataset_preparation.py -q
Pop-Location
```

The workbook reconciliation was performed with `openpyxl` in read-only mode: locate the row containing `FileName`, read its `Split-4` values in `v2-latest`, and compare the resulting ID sets with stems from `*.img.nii.gz` and `*.label.nii.gz`. The full payload pass used `nibabel.load(path, mmap=True)` followed by `numpy.asarray(image.dataobj)` one volume at a time; it compared image/mask `shape` and `affine`, checked `numpy.isfinite`, checked mask integrality, counted mask values/foreground voxels per slice, and used `nibabel.aff2axcodes(affine)`. Exact compressed-file duplicate checking used streaming `hashlib.sha256` in 4 MiB chunks. The reported affine tolerances and calculations are given above.

To build the standardized manifest in a later, separately authorized preparation, first prepare a release-specific registration JSON outside both the repository and dataset root; do not use the example below until the license and split evidence are verified:

```powershell
Push-Location backend
python -m scripts.prepare_ccta_dataset --root $DataRoot `
  --registration 'F:\path\to\registration.json' `
  --output 'F:\path\to\new-manifest.json'
Pop-Location
```

## References

1. Zeng et al., *ImageCAS: A large-scale dataset and benchmark for coronary artery segmentation based on computed tomography angiography images*, Computerized Medical Imaging and Graphics 109 (2023), 102287, [DOI](https://doi.org/10.1016/j.compmedimag.2023.102287), [arXiv manuscript](https://arxiv.org/abs/2211.01607).
2. Official project repository [README and split workbook](https://github.com/XiaoweiXu/ImageCAS-A-Large-Scale-Dataset-and-Benchmark-for-Coronary-Artery-Segmentation-based-on-CT) (the local copy of `imageCAS_data_split.xlsx` contains `v1` and `v2-latest`).
3. Local reproduction package’s `data_list/split_1000.csv` and `utils/utils.py` were inspected only to understand its separate four-fold split semantics; these do not establish a crosswalk to the official workbook IDs.
