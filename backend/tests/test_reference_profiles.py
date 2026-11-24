"""Isolated synthetic tests; run with --noconftest, no database access."""
import hashlib
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.services import reference_profiles as service
from app.routers import reference_profiles as routes
from app.core.dependencies import get_current_user, get_db
from app.core.roles import Role
from app.core.quantitative_gate import VALIDATED_GATES


@pytest.fixture
def pack(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    inputs = {}
    for name in service.INPUT_HASHES:
        value = f"synthetic-only:{name}".encode()
        (source / name).write_bytes(value)
        inputs[name] = hashlib.sha256(value).hexdigest()
    data = b'{"synthetic":"not a real reference profile"}'
    (tmp_path / "profiles.json").write_bytes(data)
    # Only this test swaps trusted identities. Runtime has no registration API.
    monkeypatch.setattr(service, "INPUT_HASHES", inputs)
    monkeypatch.setattr(service, "PROFILES_SHA256", hashlib.sha256(data).hexdigest())
    return tmp_path, data


def test_complete_pack_and_empty_clinical_registry(pack):
    root, data = pack
    assert service.load_reference_profiles(root) == data
    assert not VALIDATED_GATES


@pytest.mark.parametrize("target", ["profiles.json", "source/401.coronary.nii.gz", "source/404.coronary_left_centerline.vtk"])
def test_changed_bytes_fail_closed(pack, target):
    root, _ = pack
    with (root / target).open("ab") as stream:
        stream.write(b"forged validated:true")
    with pytest.raises(service.ReferenceDisplayUnavailable):
        service.load_reference_profiles(root)


def test_missing_and_unconfigured(pack):
    root, _ = pack
    (root / "source/402.coronary.nii.gz").unlink()
    for directory in (None, root):
        with pytest.raises(service.ReferenceDisplayUnavailable):
            service.load_reference_profiles(directory)


def test_directory_instead_of_file(pack):
    root, _ = pack
    path = root / "profiles.json"
    path.unlink()
    path.mkdir()
    with pytest.raises(service.ReferenceDisplayUnavailable):
        service.load_reference_profiles(root)


@pytest.mark.parametrize("role,status", [(Role.ADMIN, 200), (Role.DATA_SCIENTIST, 200), (Role.RESEARCHER, 200), (Role.CLINICIAN, 403)])
def test_existing_role_policy(pack, monkeypatch, role, status):
    root, data = pack
    app = FastAPI()
    app.include_router(routes.router, prefix="/api/v1")
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(role=role, id=1)
    app.dependency_overrides[get_db] = lambda: SimpleNamespace(add=lambda event: None, commit=lambda: None)
    monkeypatch.setattr(routes.settings, "VASCULAI_REFERENCE_PROFILE_DIR", str(root))
    response = TestClient(app).get("/api/v1/research/reference-profiles")
    assert response.status_code == status
    if status == 200:
        assert response.content == data
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-reference-display-gate"] == service.GATE_ID


def test_missing_auth_denies_before_evidence_read(monkeypatch):
    app = FastAPI()
    app.include_router(routes.router, prefix="/api/v1")
    app.dependency_overrides[get_db] = lambda: None
    monkeypatch.setattr(routes, "load_reference_profiles", lambda path: pytest.fail("Unauthorized evidence read"))
    assert TestClient(app).get("/api/v1/research/reference-profiles").status_code == 401


def test_invalid_pack_is_sanitized_503(pack, monkeypatch):
    root, _ = pack
    (root / "profiles.json").write_bytes(b"altered")
    app = FastAPI()
    app.include_router(routes.router, prefix="/api/v1")
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(role=Role.ADMIN, id=1)
    app.dependency_overrides[get_db] = lambda: None
    monkeypatch.setattr(routes.settings, "VASCULAI_REFERENCE_PROFILE_DIR", str(root))
    response = TestClient(app).get("/api/v1/research/reference-profiles")
    assert response.status_code == 503
    assert str(root) not in response.text
