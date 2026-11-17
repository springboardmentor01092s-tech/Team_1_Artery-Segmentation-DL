"""Immutable, specifically approved reference display; not a clinical gate/provider.

Approval covers only these precomputed ImageCAS-X v2 Training profiles. Changing
the operator path cannot authorize another artifact, method, or patient case.
Dataset identifiers here are deliberately not application case identifiers.
"""
import hashlib
from pathlib import Path
from types import MappingProxyType

GATE_ID = "reference-profile/0.1"
METHOD_SHA256 = "aca8d3751a22cca9379df1d9edb3fded895b014263e94d639aee9d7ca32132a4"
PROFILES_SHA256 = "1330b37432778e1170faaec94bae7141b364b4cdfa2ec20367da93d3f156642a"
NOTICE = "reference-derived research measurement, not validated"
INPUT_HASHES = MappingProxyType({
    "401.coronary_left_centerline.vtk": "19b94c80f6ad300f3ca3135135e28ff171dc5ce946690a31faf319af6c4d3b83",
    "401.coronary_right_centerline.vtk": "a6686ae90f355cb85530c44a4fb1d11ec469a9354b42b4eadf00a0bb31eef8bb",
    "401.coronary.nii.gz": "6c4cfce27e4f61f8d38e9fddbb98fcfc7e49da44dba0ae3cb48c01229a0e5c43",
    "402.coronary_left_centerline.vtk": "769b20d747986070d47fce04a60e5e4bc6bacb2dbcf88339628e165deead8096",
    "402.coronary_right_centerline.vtk": "491d2d2ea2923d27848e080339d94d8b2e209f990aaf58198600f44c0d7342c6",
    "402.coronary.nii.gz": "93867d7a6d3dfc306e316babe2802d8d8163ae4b4d1d5ed2d129779b2bb2d032",
    "404.coronary_left_centerline.vtk": "a42c6d2f862c1fae6620df12b8053b6ee724ffa80fa4101411aadd2e94d50aaf",
    "404.coronary_right_centerline.vtk": "c7bac574107f5ab5bbf7c7c8bcfab73685914aa9eed174589f15dde6c1e088bd",
    "404.coronary.nii.gz": "f827ae59478002f85cdccaae01f69fad8bf367e664a87c12ce1d1a04c89f6cfd",
})


class ReferenceDisplayUnavailable(ValueError):
    pass


def _checked_bytes(root, name, expected, limit):
    path = root / name
    if path.is_symlink() or not path.is_file() or path.resolve().parent != root.resolve():
        raise ReferenceDisplayUnavailable("Reference evidence path is unavailable")
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit or hashlib.sha256(data).hexdigest() != expected:
        raise ReferenceDisplayUnavailable("Reference evidence does not match approved identity")
    return data


def load_reference_profiles(directory):
    """Verify actual bytes on every read; never trust supplied validation claims."""
    if not directory:
        raise ReferenceDisplayUnavailable("Reference display evidence is not configured")
    root = Path(directory)
    source = root / "source"
    if root.is_symlink() or not root.is_dir() or source.is_symlink() or not source.is_dir():
        raise ReferenceDisplayUnavailable("Reference evidence directory is unavailable")
    if source.resolve().parent != root.resolve():
        raise ReferenceDisplayUnavailable("Reference source directory is outside evidence root")
    for name, expected in INPUT_HASHES.items():
        _checked_bytes(source, name, expected, 1_048_576)
    # Exact artifact hash binds all section values, nulls/reasons, provenance and
    # limitations. No recomputation, gate promotion, or result persistence here.
    return _checked_bytes(root, "profiles.json", PROFILES_SHA256, 8_388_608)
