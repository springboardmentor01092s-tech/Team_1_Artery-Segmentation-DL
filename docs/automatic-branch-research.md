# Restricted automatic branch research — offline, unvalidated

The existing Lee/raw-graph extractor and all refusal rules remain unchanged.
`automatic_branch_plan.py` adds an integrity-checked bridge from an admitted tree
to the existing sampler. It checks native coordinates, source binding, complete
edge/vertex partitioning, unique paths and a 2 MiB evidence budget. Refused graphs
retain diagnostic evidence but emit no sampling branches. No pruning, component
selection, invented points, inference, database writes or clinical gate exists.

## Explicit source-bound file workflow

`backend/scripts/research_automatic_branches.py` accepts explicit original CT,
mask and request files. It does not discover datasets. Request schema
`automatic-branch-request/0.1` has exactly: `schema_version`, `dataset_split`
(`Training` or `synthetic`), `spatial_scope` (`numerical_native_grid_only`), actual
`ct_sha256`, `mask_file_sha256`, `source`, exact `geometry` and explicit existing
`parameters`. Source retains CT/canonical-mask hashes, geometry fingerprint, mask
role, actual parent run identity where applicable and target label.

The CLI requires coded CT/mask millimetre geometry, exact affine agreement,
unscaled uint8 NIfTI-1 mask storage and at most 4,000,000 voxels. Unknown mask units
are refused, not inferred. It does not resample/relabel or edit original bytes.
Hashes are rechecked before publication. Only a new external directory is allowed;
collisions never overwrite. Refusals/failures are explicit and preserve evidence.

An admitted run emits `branch-evidence.json`, `profile-plan.json` in the existing
`research-profile-plan/0.1` format, and `RUN.json` with source/request/implementation
identities. A refusal emits no sampling plan. Use an admitted plan with the existing
`research_candidate_profile.py`; deterministic ordering does not identify anatomical
proximal/distal direction. Browser import additionally requires a matching actual
stored run and authenticated recomputation. Never invent its ID.

An operator's split/role statement is not a dataset, licence or stored-run
attestation. Identity hashes are not signatures or proof of clinical correctness.

## Synthetic acceptance

Tests: `test_automatic_branch_plan.py`, `test_automatic_branch_cli.py`.
The new 14-case analytic set covers straight/curved/anisotropic vessels, Y and
multi-junction trees, narrow vessels, rotated geometry, disconnected components,
loops, spurs/noise, even widths, ambiguous junctions, boundary contact and empty
masks. Invalid sources/geometry/labels, integrity and file limits are tested separately.
The frozen twenty-case matrix and instrumentation were not rerun or tuned.

Four configurations admit trees: narrow, Y, multi-branch and oblique Y. Ten abstain,
including anisotropic Y at the unchanged support guard. Admitted trees retain
expected topology, complete sampled-curve coverage within two native voxel
diagonals, bounded displacement/endpoints and zero false/missing matched branches.
Matching uses independent analytic endpoint pairs, not only counts. These are
discretization-scale engineering checks, not anatomical/clinical accuracy.

General robust extraction remains unresolved. Supplied centerlines remain the
fallback. Larger tiled-profile limits do not enlarge automatic or browser limits.

The scikit-image reference explains Lee thinning, not anatomical branch completeness
for our masks. VMTK's documented surface/Voronoi radius-weighted approach requires
an additional surface/seed pipeline and validation; it was investigated, not
installed or claimed working. Sources: [scikit-image](https://scikit-image.org/docs/stable/auto_examples/edges/plot_skeleton.html),
[VMTK](https://vmtk.github.io/tutorials/Centerlines.html).

No classifier, expert label, validated percentage/severity, calibrated confidence
or stenosis attribution was generated. Both authorization flags remain false.
