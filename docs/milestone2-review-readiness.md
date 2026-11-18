# VascuAI Milestone 2: review readiness

Prepared 31 October 2026. Repository: `main` at
`d164d158729e15323b35b2faf1b3977ecf54ce2a`.

## 1. Executive summary

The experimental baseline segmentation implementation, trained checkpoint,
saved validation predictions and CT/prediction viewer provide demonstrable
progress. Frozen results exist for two validation cases, with substantial
segmentation limitations. An advanced architecture and a defensible model-selection
comparison are not complete. Vessel analysis remains an unmerged standalone
prototype requiring independent review of its latest revision. This is a readiness
summary, not a claim of complete milestone acceptance or clinical validation.

Existing web audits, the case-851 failure audit and the frozen performance report
serve different purposes. This document summarizes and links their evidence; it
does not replace them or introduce an evaluation methodology.

## 2. Milestone status

| Milestone task | Status | Evidence-based explanation |
|---|---|---|
| Baseline segmentation model | Complete | Experimental `SmallUNet3D(base=8)`, 85,177 parameters; implementation and compatible saved weights exist. CPU strict-loading was verified in the 29 October audit, without inference. |
| Advanced segmentation architecture | Missing | No implemented distinct advanced architecture identified. Available checkpoint variants remain SmallUNet3D. |
| Model checkpoints and training | Partial | Weighted baseline and other compatible variants exist. Recovered Kaggle notebooks contain training code, but reproducible local training, source-data readiness and complete checkpoint lineage remain unresolved. |
| Segmentation mask generation | Complete | Scope: existing frozen baseline runs for cases 851/852 contain binary masks, probability volumes, metadata and successful execution records. No new generation is claimed here. |
| Post-processing | Partial | Configurable component filtering exists in PR #12, not merged into the application. Frozen predictions have no post-processing. |
| Vessel structure and centerline extraction | Partial | Standalone Lee skeletonization and revised loss diagnostics exist in PR #12. Even-width component disappearance remains an algorithm limitation; latest changes need independent review. |
| Vessel diameter estimation | Partial | PR #12 uses spacing-aware EDT and twice-radius estimates at centerline voxels. These are approximate research measurements, not validated clinical diameters. |
| Model comparison | Partial | Historical baseline/pilot results exist, but no fully reproducible architecture comparison or justified winner has been established. |
| Segmentation performance reporting | Partial | Reproducible saved two-case metrics exist; they do not establish full-fold, full-dataset or clinical performance. |

Implementation evidence:
[model.py](F:/Documents/artery_demo/backend/app/services/segmentation/model.py),
[inference.py](F:/Documents/artery_demo/backend/app/services/segmentation/inference.py),
[integration guide](F:/Documents/artery_demo/backend/app/services/segmentation/README.md),
and [viewer guide](F:/Documents/artery_demo/docs/frontend-segmentation-viewer.md).

## 3. Existing segmentation performance

Frozen run:
`F:/Documents/vascuai-artifacts/runs/two-case-step700-thr070-20261020T084831Z`.

The [evaluation CSV](F:/Documents/vascuai-artifacts/runs/two-case-step700-thr070-20261020T084831Z/evaluation.csv)
and [evaluation JSON](F:/Documents/vascuai-artifacts/runs/two-case-step700-thr070-20261020T084831Z/evaluation.json)
agree on every value below. Metrics are displayed to six decimal places from the
existing results; no missing score or new volume-based evaluation was calculated.

| Validation case | Dice | IoU | Precision | Recall | Recorded pipeline duration (s) |
|---|---:|---:|---:|---:|---:|
| 851 | 0.131794 | 0.070546 | 0.079576 | 0.383338 | 180.263 |
| 852 | 0.105938 | 0.055931 | 0.060600 | 0.420643 | 287.783 |

Durations come from
[case-851 metadata](F:/Documents/vascuai-artifacts/runs/two-case-step700-thr070-20261020T084831Z/case-851/metadata.json)
and [case-852 metadata](F:/Documents/vascuai-artifacts/runs/two-case-step700-thr070-20261020T084831Z/case-852/metadata.json).
They are recorded pipeline durations, including preparation/loading and output
work, not isolated model-forward latency or GPU benchmarks. Process wall times
in `execution-summary.json` are a separate measurement and are not substituted.

Evaluated checkpoint:
`F:/Documents/artery_demo/model/vascuai_model_handoff_for_codex_20261016/vascuai_model_handoff_recovered/model/artery_unet_10case_weighted_step700.pt`.
SHA-256: `e208fa586bb9bb50dc77b913caa0355a547bad529f9f0d61df17880b2efc5254`.

The frozen protocol uses threshold **0.70**, CT clipping to [-200, 800] followed
by `(image + 200) / 1000`, 64-cubed patches, stride 32, sigmoid-then-average
overlap aggregation, and reference foreground `label > 0`. Neither threshold
selection nor post-processing was performed for this frozen run. Split-4
workbook/export evidence assigns both cases to validation. The saved
[report](F:/Documents/vascuai-artifacts/runs/two-case-step700-thr070-20261020T084831Z/report.md),
`execution-protocol.json`, `verification.json`, per-case provenance and
`SHA256SUMS.txt` retain the detailed records.

**This is a preliminary two-case diagnostic, not full-dataset validation or
clinical validation.** Both references declare unknown spatial units. Existing
evaluation explicitly assumes voxelwise alignment after numerical grid checks;
matching headers do not independently establish anatomical registration or
annotation completeness. No physical-volume metric is justified. Case 851's
original publisher-version binding also remains unresolved. Checkpoint metadata
records step 700 while optimizer counters record 300; the original execution
lineage is not fully established. No new training-history conclusion is implied.

## 4. Model comparison status

The archived latest/step-400, balanced/step-700, weighted/step-700 and hard-negative
pilot/step-800 weights are **variants of SmallUNet3D**, not separate baseline and
advanced architectures. Locations are
`F:/Downloads/BACKUP/14.10.2026/artery_experiment_backup.zip` and
`F:/Downloads/BACKUP/17.10.2026/artery_unet_hard_negative_pilot_step800.pt`.

`F:/Downloads/BACKUP/17.10.2026/baseline_vs_pilot_validation.csv` contains 144
historical rows for two checkpoint labels, cases 852-855 and 18 thresholds. It
lacks source/checkpoint hashes and complete execution provenance; original local
CT/reference pairs for 853-855 have not been established. The CSV alone cannot
support a fully reproducible comparison or a model-selection claim. No winner
is selected here.

Before selection, verify checkpoint/training lineage and data separation, freeze
the same eligible validation cohort and reference interpretation, and document
checkpoint-compatible preprocessing, geometry, threshold, post-processing policy,
metric/empty-case conventions, aggregation, hardware and timing boundaries.
Preserve source/output hashes and scripts. Do not choose thresholds from the
historical sweep or access held-out test images. A baseline/pilot checkpoint
comparison would still not fulfill a distinct advanced-architecture comparison.

## 5. Vessel-analysis status and evidence dates

[PR #12](https://github.com/vimalluuu/artery_demo/pull/12) remains open against
`main`. Its standalone module provides 3D Lee centerlines, spacing-aware
`distance_transform_edt(..., sampling=spacing)` diameter estimates and
configurable 6/18/26-connected component filtering.

- **Earlier independent review, head `a7eed45`:** the six submitted cases passed;
  21 additional review cases produced 17 passes and four failures. Three failures
  reproduced total skeleton loss for 2x2, 4x4 and 6x6 bars. The fourth reproduced
  removal at the nominal 0.343 physical-volume threshold due to floating-point
  rounding. Branch/degenerate coverage and a technical report were missing then.
- **Current revision inspected 31 October, head `2381f4a`:** the PR now adds
  opt-in disappearance/fragmentation diagnostics, absolute threshold tolerance,
  expanded geometric tests and `docs/vessel-analysis-report.md`. The earlier
  missing tests/report must not be described as wholly absent from this revision.
  The algorithm still loses some even-width components; diagnostics expose loss
  when requested rather than restoring vessels.
- **Existing remote results:** GitHub reports successful frontend/backend checks
  for the updated revision. The inspected backend job records 312 passed,
  3 skipped and 3 warnings in each pytest invocation; skips require PyTorch.
  [Observed job log](https://github.com/vimalluuu/artery_demo/actions/runs/41042495133/job/124018445448).
  These are remote CI observations, not newly executed local tests or independent
  acceptance of the revised behavior.

Independent review of diagnostic consumption/default behavior, branch-arm and
mixed-component preservation, tolerance scale/units, geometric assertions and
documentation completeness is still required. Saish should resolve remaining
findings and obtain successful verification before merge. The PR has not been
approved or merged as part of this task.

## 6. Limitations and prioritized next actions

1. **Saish's fixes/tests:** confirm the revised diagnostics cannot be mistaken
   for successful vessel preservation, address remaining boundary/coverage gaps,
   and complete the prototype's documented verification evidence.
2. **Review the updated PR:** independently examine and retest `2381f4a` before
   any acceptance decision. Do not carry old failures forward as fresh results.
3. **Reproducible comparison:** when resources and annotations permit, approve a
   frozen checkpoint comparison with no threshold sweep; coordinate reporting
   with Muskan and any evaluation UI with Roja.
4. **Future work:** implement/train a distinct advanced architecture only after
   data, hardware, training protocol and authorization are ready.

The project environment has CPU-only PyTorch `2.14.1+cpu`. Existing readiness
inventory and the 29 October audit established no verified local Training pairs;
Kaggle-dependent notebook code is not an approved local training pipeline.
Reference units, source-version/annotation questions and checkpoint lineage
remain limitations. Do not resolve these by editing source headers or weights.
Case 852 also exceeds the unchanged default 67,108,864-voxel inference/viewer cap;
prefer existing case-851 evidence for a bounded demonstration, with a saved-output
fallback. No memory-limit change or silent downsampling is proposed.

Preparation verification on 31 October checked CSV/JSON agreement, metadata and
implementation consistency, and hashes of eight consulted frozen reporting files
against their existing manifest. No fresh tests, inference, training, database
operations, dataset processing or clinical assessment were performed. Existing
performance reports, predictions and teammate files were left unchanged.

## 7. Meeting summary (60-90 seconds)

> We have implemented an experimental 3D U-Net baseline and integrated saved
> segmentation results into the application's CT viewer. We have frozen,
> reproducible diagnostic results for two validation cases, including Dice, IoU,
> precision, recall and recorded pipeline durations. Dice is approximately 0.132
> and 0.106, so these results show substantial limitations rather than clinical
> readiness. Both reference masks have unknown spatial units; evaluation relies
> on an explicit voxelwise-alignment assumption. Saish's standalone vessel-analysis
> PR includes centerlines, spacing-aware diameter estimates and component
> filtering. Its latest revision adds diagnostics, tests and documentation in
> response to review, but independent verification is still needed before merge.
> We have several checkpoints of the same SmallUNet3D architecture, not a completed
> advanced architecture. Our next priorities are reviewing the vessel fixes,
> making checkpoint comparison reproducible, and resolving training-data and
> hardware readiness before advanced-model training. This is verified prototype
> progress, not complete milestone acceptance or clinical validation.
