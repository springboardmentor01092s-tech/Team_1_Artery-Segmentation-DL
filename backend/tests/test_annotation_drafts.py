"""Synthetic, private test schema only. No labels, inference or application data."""
from concurrent.futures import ThreadPoolExecutor
import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from threading import Barrier, Lock
from uuid import uuid4

import jwt
import nibabel as nib
import numpy as np
import pytest
from fastapi import HTTPException
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.annotation_body import AnnotationBodyLimit
from app.database.session import SessionLocal
from app.models import Case, User
from app.models.annotation_draft import AnnotationDraft
from app.models.segmentation import SegmentationResult
from app.schemas.annotation_draft import AnnotationDocument, FALSE_FIELDS, POINT_FIELDS
from app.services import annotation_drafts as service
from conftest import PASSWORD


def ct_bytes():
    image = nib.Nifti1Image(np.zeros((5, 7, 9), dtype=np.int16), np.eye(4))
    image.header.set_xyzt_units("mm")
    return gzip.compress(image.to_bytes())


def document(source):
    return dict(schema_version="lesion-annotation-workspace/0.1", source=source,
        status="unverified_local_draft", label_origin="manual_reader_preparation_not_expert_ground_truth",
        algorithm_exposure="predicted_segmentation_available_in_workspace", **{key: False for key in FALSE_FIELDS},
        reviewer_reference="", protocol_reference="", proposed_lesions=[])


def worksheet():
    return dict(draft_id=str(uuid4()), artery="", segment="", segment_convention="",
        **{key: None for key in POINT_FIELDS}, minimum_lumen_diameter_mm=None,
        adjacent_reference_diameter_mm=None, reference_selection="", percentage_narrowing=None,
        percentage_basis="", severity_category=None, unavailable_reason="Unrecorded synthetic software fixture", notes="")


@pytest.fixture
def prepared(client, account, db):
    owner, headers = account("Clinician")
    patient = client.post("/api/v1/patients", headers=headers,
        json={"patient_code": uuid4().hex, "display_name": "Synthetic annotation test"}).json()
    case = client.post("/api/v1/cases", headers=headers,
        json={"patient_id": patient["id"], "case_code": uuid4().hex, "modality": "CTA"}).json()
    data = ct_bytes()
    assert client.post(f"/api/v1/cases/{case['id']}/volume", headers=headers,
        files={"file": ("software-fixture.nii.gz", data)}).status_code == 200
    stored = db.get(Case, case["id"])
    run_id = str(uuid4())
    folder = Path(settings.OUTPUT_DIR) / "segmentations" / run_id
    folder.mkdir(parents=True)
    for name in ("prediction_mask.nii.gz", "probabilities.nii.gz"):
        (folder / name).write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    source = dict(case_id=case["id"], source_sha256=digest, segmentation_result_id=run_id,
                  shape=[5, 7, 9], affine=np.eye(4).tolist(), units="mm")
    db.add(SegmentationResult(id=run_id, case_id=case["id"], source_volume_path=stored.volume_path,
        created_by=owner.id, metadata_json=dict(source_sha256=digest, shape=[5, 7, 9], affine=np.eye(4).tolist(),
                                               xyzt_units=2, checkpoint_sha256="a"*64, threshold=0.5)))
    db.commit()
    return dict(owner=owner, headers=headers, case_id=case["id"], patient_id=patient["id"], run_id=run_id,
                source=source, document=document(source), path=Path(settings.UPLOAD_DIR)/stored.volume_path,
                folder=folder, url=f"/api/v1/cases/{case['id']}/annotation-drafts")


def create(client, prepared, headers=None, doc=None):
    return client.post(prepared["url"], headers=headers or prepared["headers"],
                       json={"document": doc if doc is not None else prepared["document"]})


def test_create_retrieve_update_delete_and_unverified_provenance(client, prepared, db):
    before = deepcopy(prepared["document"])
    response = create(client, prepared)
    assert response.status_code == 201, response.text
    saved = response.json()
    assert saved["revision"] == 1 and saved["source_current"] is True
    assert saved["patient_id"] == prepared["patient_id"] and saved["owner_id"] == prepared["owner"].id
    assert saved["document"] == before == prepared["document"]
    assert saved["segmentation_provenance"] == dict(segmentation_result_id=prepared["run_id"], checkpoint_sha256="a"*64,
        mask_sha256=prepared["source"]["source_sha256"], probabilities_sha256=prepared["source"]["source_sha256"], threshold=0.5)
    assert saved["geometry_identity"]["version"] == "ct-geometry/1.0" and len(saved["geometry_identity"]["sha256"]) == 64
    assert saved["clinical_gate_authorized"] is saved["training_release_authorized"] is False
    url = prepared["url"] + "/" + saved["id"]
    read = client.get(url, headers=prepared["headers"])
    assert read.status_code == 200 and read.headers["cache-control"] == "no-store"
    doc = deepcopy(before);doc["proposed_lesions"] = [worksheet()]
    doc["proposed_lesions"][0]["minimum_lumen_diameter_mm"] = 0
    updated = client.put(url, headers=prepared["headers"], json={"expected_revision": 1, "document": doc})
    assert updated.status_code == 200, updated.text
    assert updated.json()["revision"] == 2 and updated.json()["document"] == doc
    assert client.delete(url, headers=prepared["headers"], params={"expected_revision": 1}).status_code == 409
    assert client.delete(url, headers=prepared["headers"], params={"expected_revision": 2}).status_code == 204
    assert client.get(url, headers=prepared["headers"]).status_code == 404
    assert db.scalar(select(func.count()).select_from(AnnotationDraft)) == 0


@pytest.mark.parametrize("other_role", ["Clinician", "Admin"])
def test_discovery_filters_owner_before_pagination_without_leaking_findings(client, prepared, account, other_role):
    saved = create(client, prepared).json()
    other, headers = account(other_role)
    hidden_only = client.get(prepared["url"], headers=headers, params={"limit": 1})
    assert hidden_only.status_code == 200
    assert hidden_only.json() == dict(items=[], limit=1, offset=0, next_offset=None, offset_limit_reached=False)
    own_other = create(client, prepared, headers).json()
    page = client.get(prepared["url"], headers=prepared["headers"], params={"limit": 1}).json()
    assert [row["id"] for row in page["items"]] == [saved["id"]] and page["next_offset"] is None
    assert all("document" not in row and "patient_id" not in row for row in page["items"])
    other_page = client.get(prepared["url"], headers=headers).json()
    assert [row["id"] for row in other_page["items"]] == [own_other["id"]]
    assert all(row["owner_id"] == other.id and row["clinical_gate_authorized"] is False
               and row["training_release_authorized"] is False for row in other_page["items"])


def test_discovery_pages_and_run_filter_survive_logout_login(client, prepared):
    first = create(client, prepared).json();second = create(client, prepared).json()
    page = client.get(prepared["url"], headers=prepared["headers"], params={"limit": 1}).json()
    assert page["next_offset"] == 1
    other = client.get(prepared["url"], headers=prepared["headers"], params={"limit": 1, "offset": 1}).json()
    assert {page["items"][0]["id"], other["items"][0]["id"]} == {first["id"], second["id"]}
    assert other["next_offset"] is None
    assert client.get(prepared["url"], headers=prepared["headers"],
        params={"segmentation_result_id": str(uuid4())}).json()["items"] == []
    assert client.post("/api/v1/auth/logout", headers=prepared["headers"]).status_code == 204
    assert client.get(prepared["url"], headers=prepared["headers"]).status_code == 401
    login = client.post("/api/v1/auth/login", json={"email": prepared["owner"].email, "password": PASSWORD}).json()
    headers = {"Authorization": "Bearer " + login["access_token"]}
    rows = client.get(prepared["url"], headers=headers,
        params={"segmentation_result_id": prepared["run_id"]}).json()["items"]
    assert {row["id"] for row in rows} == {first["id"], second["id"]}
    assert client.get(prepared["url"], headers=headers, params={"offset": 1_000_001}).status_code == 422


@pytest.mark.parametrize("role", ["Researcher", "DataScientist"])
def test_discovery_requires_current_writer_role(client, prepared, account, role):
    _, headers = account(role)
    assert client.get(prepared["url"], headers=headers).status_code == 403
    assert client.get(prepared["url"]).status_code == 401


@pytest.mark.parametrize("role", ["Admin", "Clinician"])
def test_other_authors_including_admin_cannot_read_change_delete(client, prepared, account, role):
    saved = create(client, prepared).json()
    _, headers = account(role)
    url = prepared["url"] + "/" + saved["id"]
    assert client.get(url, headers=headers).status_code == 404
    assert client.put(url, headers=headers, json={"document": prepared["document"], "expected_revision": 1}).status_code == 404
    assert client.delete(url, headers=headers, params={"expected_revision": 1}).status_code == 404
    assert client.get(url, headers=prepared["headers"]).json()["revision"] == 1


@pytest.mark.parametrize("role", ["Researcher", "DataScientist"])
def test_nonwriters_rejected_for_every_route(client, prepared, account, role):
    saved = create(client, prepared).json();url = prepared["url"] + "/" + saved["id"]
    _, headers = account(role)
    assert create(client, prepared, headers).status_code == 403
    assert client.get(url, headers=headers).status_code == 403
    assert client.put(url, headers=headers, json={"document": prepared["document"], "expected_revision": 1}).status_code == 403
    assert client.delete(url, headers=headers, params={"expected_revision": 1}).status_code == 403


def test_admin_can_author_own_draft(client, prepared, account):
    owner, headers = account("Admin")
    result = create(client, prepared, headers)
    assert result.status_code == 201 and result.json()["owner_id"] == owner.id


def test_authentication_expiry_logout_login_and_persistence(client, prepared):
    saved = create(client, prepared).json();url = prepared["url"] + "/" + saved["id"]
    assert client.post(prepared["url"], json={"document": prepared["document"]}).status_code == 401
    assert client.get(url).status_code == 401
    old = prepared["headers"]["Authorization"].split()[1]
    claims = jwt.decode(old, options={"verify_signature": False});claims["exp"] = datetime.now(timezone.utc)-timedelta(minutes=1)
    expired = jwt.encode(claims, settings.SECRET_KEY.get_secret_value(), algorithm=settings.ALGORITHM)
    assert client.get(url, headers={"Authorization": "Bearer " + expired}).status_code == 401
    assert client.post("/api/v1/auth/logout", headers=prepared["headers"]).status_code == 204
    assert client.get(url, headers=prepared["headers"]).status_code == 401
    login = client.post("/api/v1/auth/login", json={"email": prepared["owner"].email, "password": PASSWORD})
    assert login.status_code == 200
    new = {"Authorization": "Bearer " + login.json()["access_token"]}
    assert client.get(url, headers=new).json()["document"] == prepared["document"]


@pytest.mark.parametrize("kind", ["case", "hash", "shape", "affine", "run", "units", "singular", "invalid"])
def test_invalid_or_mismatched_source_does_not_persist(client, prepared, db, kind):
    doc = deepcopy(prepared["document"])
    if kind == "case":doc["source"]["case_id"] += 1
    if kind == "hash":doc["source"]["source_sha256"] = "b"*64
    if kind == "shape":doc["source"]["shape"][0] += 1
    if kind == "affine":doc["source"]["affine"][0][3] += 1
    if kind == "run":doc["source"]["segmentation_result_id"] = str(uuid4())
    if kind == "units":doc["source"]["units"] = "m"
    if kind == "singular":doc["source"]["affine"][0] = [0, 0, 0, 0]
    if kind == "invalid":doc["source"]["affine"][3][0] = 1
    assert create(client, prepared, doc=doc).status_code == (422 if kind in {"units", "singular", "invalid"} else 409)
    assert db.scalar(select(func.count()).select_from(AnnotationDraft)) == 0


def test_case_route_cannot_select_another_case_draft(client, prepared, db):
    saved = create(client, prepared).json()
    patient = client.post("/api/v1/patients", headers=prepared["headers"],
        json={"patient_code": uuid4().hex, "display_name": "Different synthetic patient"}).json()
    other = client.post("/api/v1/cases", headers=prepared["headers"],
        json={"patient_id": patient["id"], "case_code": uuid4().hex, "modality": "CTA"}).json()
    url = f"/api/v1/cases/{other['id']}/annotation-drafts/{saved['id']}"
    assert client.get(url, headers=prepared["headers"]).status_code == 404
    assert client.put(url, headers=prepared["headers"], json={"document": prepared["document"], "expected_revision": 1}).status_code == 404
    assert client.delete(url, headers=prepared["headers"], params={"expected_revision": 1}).status_code == 404
    assert client.post(f"/api/v1/cases/{other['id']}/annotation-drafts", headers=prepared["headers"],
        json={"document": prepared["document"]}).status_code == 409


def test_annotation_draft_does_not_publish_results_metrics_or_case_completion(client, prepared, db):
    tables = ("case_reviews", "stenosis_analysis_jobs", "stenosis_analysis_results", "stenosis_lesions", "evaluations", "evaluation_cases")
    before = {name: db.scalar(text(f"SELECT count(*) FROM {name}")) for name in tables}
    status = db.get(Case, prepared["case_id"]).status
    assert create(client, prepared).status_code == 201
    assert {name: db.scalar(text(f"SELECT count(*) FROM {name}")) for name in tables} == before
    db.expire_all()
    assert db.get(Case, prepared["case_id"]).status == status
    assert client.get(f"/api/v1/cases/{prepared['case_id']}/workflow", headers=prepared["headers"]).json()["review"] is None


def test_annotation_body_limit_precedes_authentication_and_parsing(client, prepared):
    response = client.post(prepared["url"], content=b"x"*(2*1024*1024+1), headers={"Content-Type": "application/json"})
    assert response.status_code == 413
    response = client.post(prepared["url"], headers={**prepared["headers"], "Content-Type": "application/json"},
                           content=b'{"document":{"source":{"affine":[NaN]}}}')
    assert response.status_code == 422


def test_streamed_request_limit_without_content_length_never_calls_parser():
    called, sent = [], []
    async def downstream(*args):called.append(True)
    chunks = iter([{"type": "http.request", "body": b"x"*1024*1024, "more_body": True}]*3)
    async def receive():return next(chunks)
    async def send(message):sent.append(message)
    middleware = AnnotationBodyLimit(downstream, prefix="/api/v1")
    asyncio.run(middleware({"type": "http", "method": "PUT", "path": "/api/v1/cases/1/annotation-drafts/id", "headers": []}, receive, send))
    assert called == [] and sent[0]["status"] == 413


@pytest.mark.parametrize("field", POINT_FIELDS)
def test_every_landmark_is_checked_against_native_shape(client, prepared, field):
    doc = deepcopy(prepared["document"]);doc["proposed_lesions"] = [worksheet()]
    doc["proposed_lesions"][0][field] = [5, 0, 0]
    assert create(client, prepared, doc=doc).status_code == 422


def test_post_flush_source_failure_rolls_back_document_and_audit(client, prepared, db, monkeypatch):
    from app.models.audit import AuditEvent
    original = service.unchanged_files
    calls = []
    def fail_second(*args):
        calls.append(True)
        if len(calls) == 2:raise HTTPException(409, "Synthetic source-version conflict")
        return original(*args)
    monkeypatch.setattr(service, "unchanged_files", fail_second)
    assert create(client, prepared).status_code == 409
    assert len(calls) == 2 and db.scalar(select(func.count()).select_from(AnnotationDraft)) == 0
    assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action == "annotation.draft_created")) == 0


@pytest.mark.parametrize("change", ["inactive", "revoked"])
def test_session_rechecked_at_write_transaction_boundary(prepared, db, change):
    with SessionLocal() as old:
        actor = old.get(User, prepared["owner"].id)
        with SessionLocal() as newer:
            values = {"is_active": False} if change == "inactive" else {"token_version": actor.token_version+1}
            newer.execute(update(User).where(User.id == actor.id).values(**values));newer.commit()
        with pytest.raises(HTTPException) as error:
            service.create_draft(old, actor, prepared["case_id"], AnnotationDocument.model_validate(prepared["document"]))
        assert error.value.status_code == 401


@pytest.mark.parametrize("flag", FALSE_FIELDS)
def test_release_and_validation_claims_cannot_be_forged(client, prepared, flag):
    doc = deepcopy(prepared["document"]);doc[flag] = True
    assert create(client, prepared, doc=doc).status_code == 422
    saved = create(client, prepared).json();url = prepared["url"] + "/" + saved["id"]
    assert client.put(url, headers=prepared["headers"], json={"document": doc, "expected_revision": 1}).status_code == 422
    assert client.get(url, headers=prepared["headers"]).json()["revision"] == 1


@pytest.mark.parametrize("extra", ["owner_id", "patient_id", "status", "clinical_gate_authorized", "training_release_authorized"])
def test_server_envelope_fields_are_not_mass_assignable(client, prepared, extra):
    assert client.post(prepared["url"], headers=prepared["headers"],
        json={"document": prepared["document"], extra: 1}).status_code == 422


def test_revision_required_and_stale_save_never_overwrites(client, prepared):
    saved = create(client, prepared).json();url = prepared["url"] + "/" + saved["id"]
    assert client.put(url, headers=prepared["headers"], json={"document": prepared["document"]}).status_code == 422
    assert client.delete(url, headers=prepared["headers"]).status_code == 422
    changed = deepcopy(prepared["document"]);changed["reviewer_reference"] = "synthetic revision two"
    assert client.put(url, headers=prepared["headers"], json={"document": changed, "expected_revision": 1}).status_code == 200
    stale = client.put(url, headers=prepared["headers"], json={"document": prepared["document"], "expected_revision": 1})
    assert stale.status_code == 409 and "revision conflict" in stale.json()["detail"]
    assert client.get(url, headers=prepared["headers"]).json()["document"] == changed


def test_stale_source_is_explicit_retrievable_but_not_editable_and_is_deletable(client, prepared):
    saved = create(client, prepared).json();url = prepared["url"] + "/" + saved["id"]
    prepared["path"].write_bytes(b"invalidated synthetic test source")
    result = client.get(url, headers=prepared["headers"])
    assert result.status_code == 200 and result.json()["source_current"] is False
    assert result.json()["source_unavailable_reason"] and result.json()["document"] == prepared["document"]
    assert client.put(url, headers=prepared["headers"], json={"document": prepared["document"], "expected_revision": 1}).status_code == 409
    assert client.delete(url, headers=prepared["headers"], params={"expected_revision": 1}).status_code == 204


def test_changed_prediction_bytes_cannot_rebind_existing_draft(client, prepared):
    saved = create(client, prepared).json();url = prepared["url"] + "/" + saved["id"]
    (prepared["folder"] / "prediction_mask.nii.gz").write_bytes(b"different synthetic artifact")
    assert client.get(url, headers=prepared["headers"]).json()["source_current"] is False
    assert client.put(url, headers=prepared["headers"], json={"document": prepared["document"], "expected_revision": 1}).status_code == 409


def test_transaction_authorization_recheck_and_database_guards(client, prepared, db):
    saved = create(client, prepared).json()
    stale_actor_id = prepared["owner"].id
    with SessionLocal() as old:
        stale_actor = old.get(User, stale_actor_id)
        with SessionLocal() as change:
            change.execute(update(User).where(User.id == stale_actor_id).values(role="Researcher"));change.commit()
        with pytest.raises(HTTPException) as caught:
            service.create_draft(old, stale_actor, prepared["case_id"], AnnotationDocument.model_validate(prepared["document"]))
        assert caught.value.status_code == 403
    with pytest.raises(IntegrityError):
        db.execute(update(AnnotationDraft).where(AnnotationDraft.id == saved["id"]).values(revision=2));db.commit()
    db.rollback()


@pytest.mark.parametrize("field,value", [("clinical_gate_authorized", True), ("training_release_authorized", True),
    ("status", "submitted"), ("owner_id", -1), ("patient_id", -1), ("geometry_sha256", "b"*64), ("revision", 9)])
def test_database_refuses_binding_release_or_submission_mutation(client, prepared, db, field, value):
    saved = create(client, prepared).json()
    with pytest.raises(IntegrityError):
        db.execute(update(AnnotationDraft).where(AnnotationDraft.id == saved["id"]).values(**{field: value}));db.commit()
    db.rollback()
    assert client.get(prepared["url"] + "/" + saved["id"], headers=prepared["headers"]).json()["revision"] == 1


@pytest.mark.parametrize("flag", FALSE_FIELDS)
def test_database_refuses_document_release_flags_even_without_api(client, prepared, db, flag):
    saved = create(client, prepared).json()
    document = deepcopy(prepared["document"]);document[flag] = True
    with pytest.raises(IntegrityError):
        db.execute(update(AnnotationDraft).where(AnnotationDraft.id == saved["id"]).values(document=document, revision=2));db.commit()
    db.rollback()
    assert db.scalar(select(AnnotationDraft.revision)) == 1


def test_disposable_postgres_two_connections_same_revision_one_winner(client, prepared, monkeypatch, db):
    if db.bind.dialect.name != "postgresql":pytest.skip("Requires disposable PostgreSQL")
    saved = create(client, prepared).json();url = prepared["url"] + "/" + saved["id"]
    barrier, lock, connections = Barrier(2, timeout=20), Lock(), []
    original = service.owned_draft
    def both_read_same_revision(session, *args):
        row = original(session, *args)
        assert row.revision == 1
        with lock:connections.append(session.scalar(text("SELECT pg_backend_pid()")))
        barrier.wait()
        return row
    with monkeypatch.context() as patch:
        patch.setattr(service, "owned_draft", both_read_same_revision)
        def save(label):
            doc = deepcopy(prepared["document"]);doc["reviewer_reference"] = label
            return label, client.put(url, headers=prepared["headers"], json={"document": doc, "expected_revision": 1})
        with ThreadPoolExecutor(max_workers=2) as pool:results = list(pool.map(save, ["writer-a", "writer-b"]))
    assert len(connections) == len(set(connections)) == 2
    assert sorted(response.status_code for _, response in results) == [200, 409]
    winner = next(label for label, response in results if response.status_code == 200)
    latest = client.get(url, headers=prepared["headers"]).json()
    assert latest["revision"] == 2 and latest["document"]["reviewer_reference"] == winner
    assert db.scalar(select(func.count()).select_from(AnnotationDraft)) == 1
    # PostgreSQL may name its UTC zone either "UTC" or "Etc/UTC". Assert
    # the session's actual offsets match UTC in both standard and daylight
    # seasons, rather than pinning a timezone alias string.
    assert db.scalar(text("""
        SELECT bool_and(
            (instant AT TIME ZONE current_setting('TimeZone')) =
            (instant AT TIME ZONE 'UTC')
        )
        FROM (VALUES
            (TIMESTAMPTZ '2026-01-15 12:00:00+00'),
            (TIMESTAMPTZ '2026-07-15 12:00:00+00')
        ) AS samples(instant)
    """)) is True


def test_json_schema_parity_with_actual_stage1_javascript(client, prepared):
    executable = shutil.which("node")
    if executable is None:pytest.skip("Node required for cross-language contract parity")
    lib = (Path(__file__).resolve().parents[2]/"frontend-react/src/lib/annotation-draft.js").as_uri()
    good = deepcopy(prepared["document"]);good["proposed_lesions"] = [worksheet()]
    good["proposed_lesions"][0]["minimum_lumen_diameter_mm"] = 0
    docs = [prepared["document"], good]
    for kind in ["singular", "affine", "shape", "units", "flag", "outside", "duplicate", "unknown", "unicode_length"]:
        doc = deepcopy(good)
        if kind == "singular":doc["source"]["affine"][0] = [0,0,0,0]
        if kind == "affine":doc["source"]["affine"][3][0] = 1
        if kind == "shape":doc["source"]["shape"][0] = 0
        if kind == "units":doc["source"]["units"] = "m"
        if kind == "flag":doc["clinical_gate_authorized"] = True
        if kind == "outside":doc["proposed_lesions"][0]["center_ijk"] = [5,0,0]
        if kind == "duplicate":doc["proposed_lesions"].append(deepcopy(doc["proposed_lesions"][0]))
        if kind == "unknown":doc["owner_id"] = 1
        if kind == "unicode_length":doc["reviewer_reference"] = "\U0001f52c"*101
        docs.append(doc)
    expected = []
    for doc in docs:
        try:AnnotationDocument.model_validate(doc);expected.append(True)
        except ValueError:expected.append(False)
    script = f"import {{validateAnnotationDraft,annotationDraftBlob}} from {json.dumps(lib)};" + """
      let input='';for await(const c of process.stdin)input+=c;
      const result=[];for(const doc of JSON.parse(input)){
        try {validateAnnotationDraft(doc,doc.source);const saved=JSON.parse(await annotationDraftBlob(doc,doc.source).text());
          validateAnnotationDraft(saved,doc.source);result.push(true);} catch {result.push(false);}
      }console.log(JSON.stringify({result,validDocuments:JSON.parse(input).slice(0,2)}));"""
    result = subprocess.run([executable, "--input-type=module", "-e", script], input=json.dumps(docs),
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0
    exported = json.loads(result.stdout)
    assert exported["result"] == expected == [True, True] + [False]*9
    # JSON.stringify emits integral affine values as integers. PostgreSQL must
    # bind the same geometry and preserve a document actually exported by JS.
    for local in exported["validDocuments"]:
        response = create(client, prepared, doc=local)
        assert response.status_code == 201, response.text
        saved = client.get(prepared["url"] + "/" + response.json()["id"], headers=prepared["headers"]).json()
        assert saved["document"] == local
