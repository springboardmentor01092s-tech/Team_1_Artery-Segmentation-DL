# ImageCAS dataset readiness validator

This isolated research tool inspects explicit manifests and source files. It
imports no application, model, training, database or inference code. It does not
discover pairs, recover data, alter images, approve a cohort, or establish
clinical validity. Source files are opened read-only. Only `--report` explicitly
requests a new output file; stdout is the default.

## Environment and invocation

Run from the repository root with the existing environment:

```powershell
.\.venv\Scripts\python.exe -B -m tools.imagecas_readiness.validator --help
```

Python standard-library CSV, ZIP and XML modules parse manifests. The XLSX reader
supports stored numeric, shared-string and inline-string cells in one explicitly
selected worksheet. It evaluates no formulas and rejects external worksheet
relationships, duplicate members/cells, XML declarations and XML members larger
than 8 MiB. It does not silently select a different sheet. This is a limited
manifest reader, not an Excel calculation engine. No pandas/openpyxl installation
is required. NiBabel and NumPy are required for NIfTI checks; an unavailable
dependency is reported as NOT_VERIFIED, rather than installed automatically.

The existing root environment has Python 3.14.7, NiBabel 5.4.2, NumPy 2.5.4 and
pytest 9.1.1. No dependency manifests are changed by this tool.

## Actual recovered sources

The current authoritative source is:

```text
<PRIVATE_ARTIFACT_PATH>
```

Select `v2-latest`, header row 2 (equivalent to pandas `header=1`), case column
`FileName`, and split column `Split-4`. The recovered CSV is
`imagecas-v2-latest-split4.csv` in that same directory. The pair manifest is:

```text
<PRIVATE_ARTIFACT_PATH>
```

These are documented local inputs, not hardcoded production paths. No ImageCAS
source directory is inferred from the application upload directory, model
checkpoint setting or an old Kaggle mount path. The application 2D image
preprocessor and full gzip-ingestion validator are deliberately not imported:
the former has a different intensity contract, while the latter scans the
complete decompressed stream. This tool performs bounded header inspection.

The workbook's `v1` identifiers use a different namespace. Neither that sheet,
the separately recovered author workbook nor `split_1000.csv` is substituted or
mapped automatically. Source selection is explicit on every invocation.

## Header-only acceptance command

This command reads manifests and the four existing CT/reference headers. It
does not hash volume contents, scan labels or create a report:

```powershell
.\.venv\Scripts\python.exe -B -m tools.imagecas_readiness.validator `
  --split-manifest '<PRIVATE_ARTIFACT_PATH>' `
  --sheet v2-latest --header-row 2 --split-column Split-4 `
  --compare-split '<PRIVATE_ARTIFACT_PATH>' `
  --pair-manifest '<PRIVATE_ARTIFACT_PATH>' `
  --source-root '<REPOSITORY_ROOT>\model\vascuai_model_handoff_for_codex_20261016\vascuai_model_handoff_recovered\sample' `
  --source-root '<PRIVATE_ARTIFACT_PATH>' `
  --expected-counts 'Training=700,Val=50,Testing=250'
```

CSV-only use replaces `--split-manifest` with the CSV path and omits `--sheet`
and `--compare-split`. That verifies the selected CSV, **not** the workbook.
Counts are always calculated from the selected source. `--expected-counts` is
optional and supplies a separate cohort expectation; 700/50/250 is not built
into the validator. Quote the count argument if required by your shell.

## Schemas, pairing and leakage

Split CSV columns default to `FileName` and the required `--split-column`.
`--id-column` supports an explicit alternate identifier column. Case IDs must be
positive decimal integers; integer-valued decimal text and leading zeros are
canonicalized so equivalent identifiers cannot evade duplicate detection.
Labels are case-sensitive `Training`, `Val`, `Testing`.

The pair CSV uses the recovered schema:

- Required: `publisher_case_id`, `split`, `ct_path`, `reference_path`.
- Optional: `ct_sha256`, `reference_sha256`, `ct_bytes`, `reference_bytes`,
  `split_sha256`, `dataset_version`, `pairing_evidence`, `readiness_status`,
  `blockers`. These are declarations, not authenticated publisher evidence.

Relative paths resolve against the pair manifest's directory. Every source path
must resolve inside an explicitly approved, existing `--source-root`; traversal
and symlink escapes are rejected. No recursive search is performed. Duplicate
case records, cross-case/role path reuse, conflicting split declarations and
recognizable publisher/handoff filename-ID or role conflicts are reported.
Generic filenames are accepted only as explicit manifest mappings; their names
do not establish anatomical correspondence.

All selected Training/Val cases require unambiguous pair records. Testing rows
are counted and skipped before their paths are resolved, statted, hashed or
opened, even when optional scans are enabled. Ambiguous split cases are not
opened. A recorded `split_sha256` is compared with the selected CSV/export hash;
when only XLSX is supplied, its CSV binding remains unverified.

Identifier-level split conflicts are errors. With hashing enabled, identical CT
bytes across cases are an integrity/leakage blocker; identical reference bytes
are a warning because masks can legitimately match. No patient/group metadata
is supported by the recovered schema, so patient-level leakage remains
NOT_VERIFIED. A clean identifier check must not be presented as patient-level
separation. No test-volume content comparison is attempted.

## Geometry and optional payload checks

Only `.nii` / `.nii.gz` single-file NIfTI-1/2 are supported. Header inspection
retains at most 540 bytes, without image proxies or extension payloads. Gzip
buffers are bounded by the library. The tool reports shape, spacing, units,
effective affine, qform/sform codes, orientation, datatype and effective scaling.
It requires 3D positive dimensions, finite positive spacing, an invertible finite
affine and a coded transform. Conflicting coded qform/sform transforms are
rejected. CT/reference affine comparison uses `rtol=0, atol=1e-5`; spacing uses
`rtol=0, atol=1e-6`, in declared header units. No unit conversion is applied.

Unknown units produce an explicit warning and `BLOCKED_GEOMETRY`; known but
different units also block geometry. Matching grids never verify registration.
In particular, case 851's unverified source version and case 852's recorded
ready-for-review status do not automatically approve either pair. Both currently
declare mm CT units versus unknown reference units. The earlier two-case
voxelwise diagnostic consent is not generalized to training readiness.

- `--verify-hashes`: streams SHA-256 over existing eligible source files,
  compares recorded hashes, reports missing expectations/mismatches, and checks
  duplicate content. This does not rewrite any manifest. Manifest identity
  hashes are calculated even without this flag; volume hashes are not.
- `--deep-label-scan`: streams only reference voxel payloads in at most 1 MiB
  on-disk chunks, applies NIfTI scaling once, and requires finite binary `{0,1}`
  values. Extra bounded NumPy arrays hold scaled values/flags; memory is O(chunk),
  not O(volume). An empty foreground is a review warning, not automatic approval.
  Scans support endian-aware scalar integer/float dtypes and stop on truncated
  payloads. CT voxel values/calibration are not scanned. Declared data offsets
  must be within 16 MiB to bound header/extension skipping.

These flags are opt-in. They were tested only on small synthetic images during
implementation; they are not automatically run on the real cohort. Default
header checks do not establish payload completeness, full gzip integrity, CT
calibration or label validity. Source size/timestamp/identity changes observed
during inspection block integrity; this offline tool is not an adversarial
filesystem snapshot service.

## Reports, decisions and exit codes

JSON stdout omits absolute paths, raw source strings, NIfTI free-text metadata,
patient information and underlying exception messages. It identifies cases and
roles, selected source settings and manifest hashes. No logs/caches are written
by the validator itself. Invoke Python with `-B` to suppress interpreter bytecode.

`--report <new-path>` additionally creates JSON exclusively, without overwriting
an existing file or creating parent directories. Destinations inside approved
source roots or any input manifest's directory are refused. Choose a separate
coordinator-owned reporting directory and protect reports appropriately.

Overall status precedence is: BLOCKED_MANIFEST, BLOCKED_INTEGRITY,
BLOCKED_MISSING_DATA, BLOCKED_GEOMETRY, NOT_VERIFIED, then READY_FOR_REVIEW.
`blocking_statuses` retains all contributing categories; each issue separately
records error, warning or unverified severity. Missing optional scans prevent a
READY_FOR_REVIEW result. Missing provenance declarations/recorded blockers also
remain unverified. READY_FOR_REVIEW still means human review is required, not
training or medical approval.

Exit codes: 0 = READY_FOR_REVIEW; 1 = blocked/not verified; 2 = CLI usage or
explicit report-output failure. A successful exit never implies clinical validity.

Expected current header-only summary (recompute; not a hardcoded result):

```json
{
  "status": "BLOCKED_MISSING_DATA",
  "split_counts": {"Training": 700, "Val": 50, "Testing": 250},
  "pair_records": 750,
  "existing_ct": 2,
  "missing_ct": 748,
  "existing_reference": 2,
  "missing_reference": 748,
  "complete_pairs": 2,
  "unknown_unit_pairs": 2,
  "anatomical_registration": "NOT_VERIFIED"
}
```

## Isolated tests

```powershell
.\.venv\Scripts\python.exe -B -m pytest tools/imagecas_readiness/tests/test_validator.py -q -p no:cacheprovider
```

The tests create only small synthetic volumes/manifests in temporary directories.
They do not import application fixtures or read the actual ImageCAS dataset.
The optional symlink regression is skipped if Windows denies symlink creation.
