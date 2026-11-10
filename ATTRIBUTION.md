# Attribution and external-artifact boundaries

This VascuAI source snapshot is prepared for the Infosys Springboard Team 1
internship review. The project owner confirmed permission to include team
contributions and the project-supplied SmallUNet3D/inference handoff code. This
statement records that confirmation; it does not independently verify every
contribution's authorship or reconstruct original model training provenance.

Git history attributes project changes to the accounts vimalluuu and CoderLink06,
with Vimal Raj also appearing in merge history. In particular, vessel-analysis
utilities/tests/documentation have CoderLink06 attribution. These account names are
not asserted to be a complete roster or proof of sole authorship. SmallUNet3D and
its inference integration were copied/adapted from the project-provided handoff.
No separate advanced architecture or original optimizer-update history is implied.

The official repository's existing LICENSE is preserved unchanged. Dependencies
retain their own licenses and notices; that file does not relicense third-party
packages, datasets, pretrained weights or marks. No dependency payload is vendored.

The frontend began with the React/Vite template. Current dependency declarations
include NiiVue (BSD-2-Clause), Lucide (ISC), React/Axios/Chart.js/fflate and related
MIT-declared packages. Development tooling also includes MPL-2.0/Apache/ISC/BSD
declarations. See package-lock.json for exact per-package versions/declarations.
Python dependencies include packages with MIT, BSD, Apache-family, LGPL and other
terms; preserve their full notices when redistributing environments or binaries.
Manifests are not a complete binary-distribution license/notice audit.

Upstream projects include [NiiVue](https://github.com/niivue/niivue),
[Lucide](https://github.com/lucide-icons/lucide), [Vite](https://github.com/vitejs/vite),
[NiBabel](https://github.com/nipy/nibabel), [scikit-image](https://github.com/scikit-image/scikit-image)
and [SciPy](https://github.com/scipy/scipy). The vessel integration invokes upstream
Lee skeletonization and distance-transform implementations; it does not claim to
have originated those algorithms.

ImageCAS is referenced as the historical segmentation dataset. No ImageCAS CT,
mask, checkpoint, split workbook, private evaluation or dataset archive is included.
Obtain external artifacts only from authorized sources and verify the exact terms
for the intended use. Availability of masks does not grant CT redistribution rights,
and the code license does not authorize medical-data redistribution or commercial
dataset use. ImageCAS-X v2 data remains excluded: its exact license was not confirmed.

Historical checkpoint naming does not establish original training-run identity or
700 optimizer updates. No clinical validation, validated quantitative stenosis,
advanced-model superiority or full-dataset performance is claimed. Genuine stenosis
and explanation providers remain unavailable; synthetic tests are not medical findings.
