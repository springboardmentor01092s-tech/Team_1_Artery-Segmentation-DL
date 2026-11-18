# Reproducible SmallUNet3D research training

This isolated package supports one CPU or one CUDA GPU. Imports start no work.
The CLI defaults to **preflight only**; execution requires `--train`. Synthetic
tests do not authorize ImageCAS training. This implementation has not been run
on Kaggle/CUDA or used for real-cohort training/validation during development.

The existing model at `app/services/segmentation/model.py` is imported unchanged:
SmallUNet3D(base=8), 85,177 parameters, single-channel NCDHW inputs and raw logits.
Production inference, APIs and dependencies are unchanged. No DataParallel/DDP,
automatic package installation or dataset/checkpoint download is performed.

## Layout

- `dataset.py`: explicit split indexing, lightweight headers, bounded single-case
  raw CT/uint8 mask cache; optional temporary disk backing.
- `sampling.py`: deterministic native-grid patches and serializable sampler state.
- `losses.py`: historical weighted BCE plus per-sample soft Dice.
- `runtime.py`: device, precision, GPU monitoring and path syntax helpers.
- `identity.py`: canonical cohort identities, pinned workbook assignments and
  optional streaming per-file SHA-256 verification.
- `validation.py`: deterministic overlapping windows with slab accumulation.
- `checkpoint.py`: restricted loading, RNG/scaler/scheduler state and atomic writes.
- `train.py`: configuration, preflight, orchestration, metrics and interruption.
- `config.example.json`: preserved original Windows/CPU configuration.
- `config.kaggle.example.json`: separate template with unverified mount placeholders.
- `tests/`: synthetic regression tests; one optional historical-weight strict-load
  check performs no forward pass or optimizer update.

## Local Windows usage

Use the existing root virtual environment; no dependency manifest was changed.
The tested runtime is Python 3.14.7, PyTorch 2.14.1+cpu, NumPy 2.5.4 and NiBabel
5.4.2. No local CUDA hardware/runtime is available. Run from `backend` so the
existing `app` package resolves normally; no `sys.path` or production-code hacks
are needed.

```powershell
Set-Location F:\Documents\artery_demo\backend
..\.venv\Scripts\python.exe -B -m training.train --help

# READ-ONLY preflight command. Not run on the recovered cohort in this task.
..\.venv\Scripts\python.exe -B -m training.train --config training/config.example.json --preflight

# Execution command FOR A SEPARATELY APPROVED RUN ONLY. Not executed here.
..\.venv\Scripts\python.exe -B -m training.train --config training/config.example.json --train
```

The local example remains byte-for-byte unchanged. Absent new optional fields
mean `device="cpu"`, `mixed_precision=false`, `gpu_monitoring=false`,
`cache_directory=null`. Config loading returns a normalized in-memory copy; it
never rewrites a config file. An explicit `--train` remains mandatory.

## Kaggle and optional RunPod execution

Use an already available compatible Python/PyTorch/NiBabel/NumPy runtime. Check
its actual versions and GPU availability rather than assuming a T4 or an exact
Kaggle runtime version. CUDA kernels/FP16 performance are unverified locally.

Bring the backend code, a verified manifest, the hash-identified optional weights
and **read-only Training/Val input roots** into the execution environment. Replace
the `SET_VERIFIED_*_MOUNT` placeholders in a separate configuration copy with
actual verified paths. The template names no real Kaggle dataset slug.

Do not assume the approximately 63.66 GiB extracted cohort fits in Kaggle's
persistent output storage. The code reads native `.nii.gz` members from the input
root; it does not stage or extract the cohort into `/kaggle/working`. Output and
optional cache space must be budgeted independently against actual quotas.

From the uploaded repository's `backend` directory:

```bash
# Inspect/prepare configuration first; this command does not train.
python -B -m training.train --config /kaggle/working/verified-training-config.json --preflight

# Separate approval required. Set this before starting the CUDA process.
# No environment setting or command below was executed during implementation.
CUBLAS_WORKSPACE_CONFIG=:4096:8 python -B -m training.train \
  --config /kaggle/working/verified-training-config.json --train
```

The same POSIX configuration structure works for a verified RunPod mount; no
provider-specific paths or GPU names are hardcoded. Native path containment is
checked on the execution host. Windows and POSIX absolute configuration syntax
can be validated on either host, but preflight refuses foreign-OS paths instead
of interpreting `/kaggle/...` as a Windows drive-relative directory.

## Device and mixed precision

Optional configuration fields:

```json
{"device": "auto", "mixed_precision": false, "gpu_monitoring": true, "cache_directory": null}
```

- `auto`: CUDA logical device 0 when available, otherwise CPU.
- `cpu`: CPU even when CUDA exists.
- `cuda`: fail clearly when unavailable; use only logical GPU 0.
- `mixed_precision=true`: CUDA FP16 autocast for forward passes and GradScaler;
  reject CPU selection, including an `auto` fallback to CPU. Disable the flag
  explicitly for a float32 CPU run. There is no CPU BF16 mode.

Parameters remain float32. Batches and model move to the selected device. Loss,
sigmoid probabilities used for metrics, overlap sums and numerical reductions
use float32 in the production training/validation paths. `unscale_` precedes
gradient checking/clipping, then scaler step/update. A normal AMP overflow skips
the optimizer update, reduces the scale and is logged explicitly. Non-finite
losses and non-AMP gradient errors stop execution; they are not swallowed.

`global_step` counts completed sampled batches, including scaler-skipped batches;
`optimizer_updates` separately counts actual updates. BatchNorm may update during
an overflowing forward; both counters/state and the reduced scale are saved.

Deterministic algorithms are required, cuDNN benchmarking and TF32 are disabled,
and CUDA execution requires `CUBLAS_WORKSPACE_CONFIG=:4096:8` (or `:16:8`) before
starting the process. Unsupported deterministic operations raise rather than
silently falling back. Performance costs have not been benchmarked.

## Dataset, geometry and bounded cache

The local root is
`F:/Documents/vascuai-artifacts/datasets/imagecas-split4-extracted-20261101`.
Its manifest is
`F:/Documents/vascuai-artifacts/diagnostics/imagecas-split4-extraction-manifest-20261101/imagecas-v2-latest-split4-manifest.csv`.

Read BOM-safe CSV fields `case_id,split,archive_group,ct_member,mask_member`.
Training/Val pairs must match exact case/member names and approved directory
structure. Duplicate IDs, missing partners, traversal and root escapes fail.
Testing records are excluded **before** resolving/statting/opening member paths.
Preflight expects the configured 700 Training/50 Val counts and reports excluded
Testing metadata; no Testing volume is read.

Headers require matching native 3D shapes, positive spacing, coded sforms and LAS
orientation. Uncoded qform differences are not registration evidence. CT mm /
unknown mask units are explicitly allowed only for voxel-grid segmentation.
**Physical measurements are unauthorized; matching numerical grids do not prove
anatomical registration.** No header edits, reorientation, interpolation or 1 mm
isotropic resampling occurs.

The cache holds one raw int16 CT and one uint8 mask at most, with a default
512 MiB byte budget. Float64 mask payloads are streamed in 1 MiB chunks, validated
as finite 0/1 values before conversion; no whole float64 mask is retained. CT
patches/targets are float32. Defaults remain batch 1, workers 0, pinning false,
threads 2. Largest recorded raw-CT/uint8-mask storage is about 208 MiB; temporary
arrays, activations and optimizer/interrupt snapshots require additional memory.

`cache_directory=null` uses RAM. An explicitly supplied writable directory uses
owned temporary memmaps for **one case**, not a full-cohort cache. It must be
outside the repository/input/manifest directories. Eviction/failure/normal exit
closes mappings and removes only that instance's temporary files. Existing cache
directory contents are preserved. Preflight creates no cache or output directory.
A forced process kill can leave owned temporary files; inspect them separately
rather than deleting arbitrary directories. Repeated gzip reads remain a CPU/IO
cost; grouped sampling reduces reloads without altering source files.

## Historical numerical recipe and documented deviations

The October 14 notebook's cells 86/92 define the implemented sampler/loss:

- CT: apply NIfTI scaling once, convert each patch to float32, clip `[-200,800]`,
  then add 200 and divide by 1000. Binary labels are never interpolated.
- 64 cubed patches. Random mode draw: `<0.50` foreground-centred, `<0.75`
  attempted-empty, otherwise unrestricted random. Attempted-empty makes **30**
  uniform origin attempts, accepting the first patch without foreground; if none
  succeeds, make one new unrestricted random draw. These are expected sampling
  proportions, not guaranteed positive/negative patch counts.
- Foreground sampling uses the same uniform C-order foreground rank and clamped
  centre formula as `np.argwhere`, but stores per-plane counts and only one plane's
  indices rather than all 3D coordinates.
- Mean BCE-with-logits, positive weight 5, **plus** mean per-sample soft Dice loss,
  smoothing `1e-6`; no extra half coefficients. AdamW LR `0.0002`, weight decay
  `1e-5`, betas `.9/.999`, epsilon `1e-8`, gradient norm clip 1, seed 456.
- Training patch metrics use threshold .5; full-volume Val metrics use fixed .70.
  Training patch Dice is not a validation score.

Deliberate new-experiment differences: shuffled case traversal without replacement,
eight consecutive patches per case by default (historical case choice was random
with replacement), explicit CPU/GPU determinism, non-fused/non-foreach AdamW,
optional FP16, and resumable state. No augmentation is added. Scheduler is not
enabled; serializer tests cover optional scheduler state without changing the
historical training LR recipe.

The example's 300-step budget preserves the historical weighted-stage count as
an example, not an approved 700-case training schedule. At eight patches/case,
one complete 700-case traversal takes 5,600 batches. Do not claim the 300-step
example trains a full epoch or establishes a new performance result.

## Validation

Only indexed Val cases are evaluated, in fixed ID order and inference mode.
The code reuses production `sliding_starts`, sigmoid and uniform overlapping
probability averaging with 64 cubed windows, stride 32. It accumulates one
patch-depth slab, repeating boundary-crossing patch forwards instead of keeping
all full-volume probabilities. Per-voxel accumulation order is preserved; this
is a CPU/compute tradeoff, not post-processing. FP16 validation is configurable
through the same precision flag; accumulation/metrics remain float32/count based.
Dice, IoU, precision and recall are reported per case and as unweighted macro
averages. Zero denominators are `null` with explicit undefined metrics; a missing
per-case metric makes the corresponding macro undefined. No physical metrics,
test evaluation, mesh creation or post-processing is performed. Cancellation
restores the previous model mode and does not update BatchNorm statistics.

## Initialization, checkpoints and exact resume

Historical weights are optional initialization only. Verify SHA-256
`e208fa586bb9bb50dc77b913caa0355a547bad529f9f0d61df17880b2efc5254`, load on CPU
with `weights_only=True`, require strict model keys and Training-only declared
training IDs. Always start a fresh optimizer/global step for this initialization.
No historical optimizer is restored and no original checkpoint is rewritten.

Version-3 experiment checkpoints contain model, optimizer, scaler and optional
scheduler states; global batch/update/epoch/phase counters; Python/NumPy/Torch
and selected-CUDA-device RNG states; sampler state; manifest/split/source
fingerprints; Train/Val IDs; numerical settings, complete normalized config,
environment, initialization hash and explicit validation recovery state.
Historical/v1/v2 files are not silently treated as v3 exact-resume state: old
experiment formats lack sufficient validation/identity state. No automatic
checkpoint migration is performed.

Writes use unique experiment directories and an owned same-directory temporary,
flush/fsync/close, then atomic `os.replace`. Existing destination files are
refused; there is no hard-link dependency. This assumes a private single-writer
run directory; it is not an adversarial multi-writer publication service. Resume
creates a new continuation directory, preserving old checkpoints/logs:

```bash
# Separate approval required; illustration only, not executed here.
CUBLAS_WORKSPACE_CONFIG=:4096:8 python -B -m training.train \
  --config /kaggle/working/verified-training-config.json \
  --resume /kaggle/input/VERIFIED_RUN_CHECKPOINT/step-000000100.pt --train
```

First Ctrl-C/SIGTERM requests a completed-batch stop. A raw KeyboardInterrupt
inside an update rolls back model/BN, optimizer, sampler, scaler and RNG to the
pre-batch boundary, then saves coherent state. Other exceptions propagate; the
last durable checkpoint remains the recovery point. Force-kill/power-loss
recovery is limited to fully published checkpoints, not unsaved progress.

### Durable validation recovery

At each scheduled validation step, save `step-NNNNNNNNN.pt` with
`validation_state.pending=true`, `completed=false` and `validation_step` equal
to `global_step` **before** any validation work. This save is mandatory even if
a stop signal arrived during that batch. No training update may pass this
pending boundary. Resume runs the pending validation first, including when the
requested maximum step has already been reached. Cancelled/failed validation
retains the pending checkpoint; its partial result is not accepted.

Successful validation saves `step-NNNNNNNNN-validation-completed.pt` containing
the last completed step/result and `pending=false, completed=true` before logging
or another training batch. Python/NumPy/Torch/selected-CUDA RNG and prior model
mode are restored around validation, including cancellation. Sampler and
optimizer remain unchanged by validation. Subsequent checkpoints retain that
last result. Completed results are not recalculated on resume.

The completed sibling includes the SHA-256 of its exact pending parent. If an
old pending filename is supplied and that bound completed sibling exists in
the same directory, resume selects the completed state automatically. A corrupt
or unrelated sibling fails closed. Keep both files together when copying a run,
or explicitly resume the completed file. Use the returned `latest_checkpoint`
for each continuation; an older pending checkpoint copied alone cannot discover
completion stored in a different continuation directory. Validation may repeat
after a crash **before** completion was atomically published; exactly-once
execution of unfinished work is not claimed. Published results prevent duplicate
validation, even if metrics logging was interrupted afterwards.

### Dataset identity, storage and runtime

Configuration accepts an optional `dataset_identity` object. Existing examples
default to **structural** identity; they are not silently upgraded to verified
content. Create a separate configuration copy for an approved portable run:

```json
{
  "dataset_identity": {
    "dataset_id": "ImageCAS",
    "version_id": "YOUR_EXPLICIT_IMMUTABLE_DATASET_VERSION",
    "expected_manifest_fingerprint": null,
    "provenance": {
      "workbook_path": "/kaggle/input/YOUR_VERIFIED_METADATA/imageCAS_data_split.xlsx",
      "workbook_sha256": "c4e7f0206329b57ddba653eaba02e7433f3b115e4f73e1928ea20144db9fddf1",
      "sheet": "v2-latest",
      "header_row": 2,
      "id_column": "FileName",
      "split_column": "Split-4"
    },
    "content_manifest": null,
    "content_manifest_sha256": null,
    "verify_content": false
  }
}
```

The workbook hash above is the previously recovered workbook's recorded pin,
not evidence that this task reverified the real cohort/workbook. Supply its
actual local path on Windows or verified mount on Kaggle; no download occurs.
Version IDs are explicit operator assertions of a stable dataset version, not
invented content hashes. A pinned version permits storage relocation without
claiming cryptographically verified image content. Use content verification when
byte identity is required.

- **Structural:** canonical integer case IDs, exact normalized relative CT/mask
  members, canonical JSON SHA-256 and all case-to-split assignments. CSV row
  order, BOM, line endings and `\\` versus `/` member separators do not alter
  identity. Testing metadata contributes only ID/split; Testing members are never
  resolved, statted, hashed or decoded. Structural checks do not prove content
  identity, and relocation is refused for exact resume at this level.
- **Version-pinned:** explicit nonempty version identifier **and verified
  authoritative workbook provenance**. The workbook SHA-256 must match; its
  `v2-latest`, Excel header row 2, `FileName` / `Split-4` assignments must equal
  the extraction manifest in full. ZIP/XML parsing uses stdlib only, rejects
  formulas and does not execute external links. Different assignments always
  invalidate resume. No anatomical or content correctness is implied.
- **Content-verified:** verified workbook provenance plus a SHA-256-pinned JSON
  content manifest and `verify_content=true`. Stream-hash every indexed
  Training/Val compressed CT and mask; check file versions around each hash.
  Changed bytes (including same-size changes) fail. No voxel arrays are decoded
  during hashing. Whole-file `.nii.gz` hashes are intentionally sensitive to
  re-compression and header edits. Testing records in a content manifest fail
  before any corresponding image path is used.

Content manifest format (illustrative record only; all indexed Training/Val
records and real 64-character lowercase SHA-256 values are required):

```json
{"schema_version": 1, "files": [{
  "case_id": 251, "split": "Training",
  "ct_member": "201-400/251.img.nii.gz",
  "mask_member": "201-400/251.label.nii.gz",
  "ct_sha256": "REPLACE_WITH_VERIFIED_SHA256",
  "mask_sha256": "REPLACE_WITH_VERIFIED_SHA256"
}]}
```

Set `content_manifest` to its absolute path, pin its exact file SHA-256 in
`content_manifest_sha256`, and explicitly enable verification. Hashes must come
from trusted recovery evidence; hashing arbitrary current bytes alone cannot
establish original-source provenance. The manifest must contain exactly one
record per permitted case, with canonical `/` member separators and matching
split/member mapping. A pinned content manifest without `verify_content=true`
records expected content but does **not** establish actual content identity.
Optional `expected_manifest_fingerprint` pins the canonical extraction manifest
reported by a trusted earlier preflight. Semantic edits then fail; harmless CSV
formatting changes remain equivalent.

Checkpoint `dataset_identity` contains canonical dataset/split/content/provenance
fingerprints, excluding physical paths. Separate `storage` records root, manifest
path/raw hash and file-version fingerprint (size/timestamps/device/inode). These
remain useful for active-file change detection, but are not portable identity.
Version-pinned/content-verified identity permits changed storage roots/file IDs;
structural-only exact resume conservatively requires unchanged storage. Sources
must remain immutable during a run; per-load version checks still apply.

Runtime compatibility is checked **separately**: Python/framework/library/OS,
machine/processor, selected device/GPU, precision and thread/determinism settings
must match, along with all numerical/sampling settings. Moving Windows data to
Kaggle can preserve dataset identity while still failing exact-runtime resume.
CPU-to-CUDA, GPU architecture changes, framework/OS changes and cross-hardware
bitwise exact replay are unsupported. Even matching recorded descriptors are not
a proof of identical drivers/kernels/hardware; exact numerical replay across
machines or Kaggle sessions is not guaranteed. Start a separately identified new
experiment instead of bypassing checks. Synthetic CPU tests verify continuation
state, not real CUDA execution or cross-machine bitwise equivalence.

Preflight reports identity level, verified (or absent) manifest provenance,
initialization versus exact resume, pending/completed validation state, and
separate runtime/storage compatibility. It writes no files. Content verification
is an explicit opt-in read of compressed Training/Val bytes and can be expensive;
default structural/header-only preflight still does not scan voxel payloads.

## Monitoring and verification

`gpu_monitoring=true` records actual device name, availability, total/allocated/
reserved/peak allocated bytes. CPU mode reports GPU memory fields as `null`.
Peak statistics reset at the start of an execution run; the helper can reset them
for a separately authorized benchmark. No ImageCAS benchmark was run.

```powershell
# From backend; only this isolated suite, no application/DB fixtures.
..\.venv\Scripts\python.exe -B -m pytest training/tests -q -p no:cacheprovider
```

The suite covers real CPU synthetic steps, a CPU-compatible GradScaler, mocked
CUDA selection/RNG/monitoring/autocast requests, no-overwrite atomic failures,
single-case disk-cache cleanup, pending/completed validation recovery (including
post-publication failure), exact tiny-model continuation, relocated dataset
roots, content/manifest/split rejection and metadata-only preflight reporting. It does
not verify real CUDA kernels, T4 memory limits, Kaggle mounts/quotas, RunPod,
recovered-cohort preflight, or any medical-image training/validation result.
