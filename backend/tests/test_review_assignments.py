"""Fresh synthetic accounts/CT only; no expert labels or model execution."""
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from copy import deepcopy
import hashlib
from threading import Barrier, Event
from uuid import uuid4

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError

from app.database.session import SessionLocal, engine
from app.main import app
from app.models import User
from app.models.review_assignment import ReviewStudy, ReviewAssignment, ReviewNoteDraft
from app.services import review_assignments as service
from test_annotation_drafts import prepared, create
from conftest import PASSWORD


@pytest.fixture
def pair(client, prepared, account):
    admin, ah = account("Admin")
    r1, h1 = account("Clinician");r2, h2 = account("Clinician")
    body = dict(case_id=prepared["case_id"], r1_user_id=r1.id, r2_user_id=r2.id,
                expected_ct_sha256=prepared["source"]["source_sha256"], protocol_version="synthetic-unapproved-v0.1",
                acknowledge_unverified=True)
    return dict(admin=admin, ah=ah, r1=r1, h1=h1, r2=r2, h2=h2, body=body, prepared=prepared)


def assigned(client, pair):
    result = client.post("/api/v1/review-studies", headers=pair["ah"], json=pair["body"])
    assert result.status_code == 201, result.text
    rows = result.json()["assignments"]
    return {row["slot"]: row["id"] for row in rows}


def note(notes="Synthetic private preparation", revision=0):
    return dict(notes=notes, expected_revision=revision, clinical_gate_authorized=False, training_release_authorized=False)


def test_coordinator_source_assignment_and_exact_original_ct(client, pair):
    preview = client.get("/api/v1/review-studies/source", headers=pair["ah"], params={"case_id": pair["body"]["case_id"]})
    assert preview.status_code == 200
    assert preview.json()["source"]["source_sha256"] == pair["body"]["expected_ct_sha256"]
    ids = assigned(client, pair)
    for slot, headers in [("R1", pair["h1"]), ("R2", pair["h2"])]:
        response = client.get("/api/v1/review-assignments", headers=headers)
        assert response.status_code == 200
        data = response.json();assert len(data["items"]) == 1
        item = data["items"][0]
        assert item["id"] == ids[slot] and item["slot"] == slot
        assert set(item) == {"id","reviewer_id","slot","case_id","protocol_version","source","geometry_identity",
                             "review_mode","clinical_gate_authorized","training_release_authorized","reader_independence_verified","qualification_verified"}
        assert "segmentation_result_id" not in item["source"] and item["review_mode"] == "original_ct_only"
        assert item["clinical_gate_authorized"] is item["training_release_authorized"] is False
        assert item["reader_independence_verified"] is item["qualification_verified"] is False
        source = client.get(f"/api/v1/review-assignments/{ids[slot]}/source", headers=headers)
        assert source.status_code == 200 and source.headers["cache-control"] == "no-store"
        assert hashlib.sha256(source.content).hexdigest() == pair["body"]["expected_ct_sha256"]
        assert source.content == pair["prepared"]["path"].read_bytes()


def test_cross_reader_and_admin_cannot_read_notes_or_assignment(client, pair):
    ids = assigned(client, pair)
    own = f"/api/v1/review-assignments/{ids['R1']}"
    assert client.put(own+"/draft", headers=pair["h1"], json=note()).status_code == 201
    for headers in [pair["h2"], pair["ah"]]:
        for suffix in ["", "/source", "/draft"]:
            assert client.get(own+suffix, headers=headers).status_code == 404
        assert client.put(own+"/draft", headers=headers, json=note("Unauthorized", 1)).status_code == 404
    assert client.get(own+"/draft", headers=pair["h1"]).json()["notes"] == "Synthetic private preparation"


def test_all_legacy_protected_routes_fail_closed_for_assigned_readers(client, pair):
    assigned(client, pair)
    checked = set()
    for template, operations in app.openapi()["paths"].items():
        path = template
        if not path.startswith("/api/v1/") or path.startswith(("/api/v1/auth/", "/api/v1/review-")):continue
        for name in __import__('re').findall(r"\{([^}]+)\}", path):
            value = str(pair["body"]["case_id"]) if name in {"case_id", "patient_id", "user_id"} else str(uuid4())
            path = path.replace("{"+name+"}", value)
        for method in {key.upper() for key in operations} & {"GET","POST","PUT","PATCH","DELETE"}:
            for headers in [pair["h1"], pair["h2"]]:
                response = client.request(method, path, headers=headers, json={} if method in {"POST","PUT","PATCH"} else None)
                assert response.status_code == 403, (method,path,response.status_code)
                assert "assigned account" in response.json()["detail"]
            checked.add((method,template))
    assert any("image" in path for _,path in checked)
    assert any("segmentations" in path for _,path in checked)
    assert any("evaluations" in path for _,path in checked)
    assert any("stenosis" in path for _,path in checked)
    assert any("workflow" in path for _,path in checked)
    assert len(checked) > 35
    # Stage 4 has no registered submission route; unknown paths return 404.
    assert client.get("/api/v1/review-assignments/00000000-0000-4000-8000-000000000000/submissions",headers=pair["h1"]).status_code == 404


@pytest.mark.parametrize("kind", ["same_reader", "admin_reader", "wrong_hash", "no_ack", "empty_protocol"])
def test_invalid_assignment_is_atomic(client, pair, db, kind):
    body = deepcopy(pair["body"])
    if kind == "same_reader":body["r2_user_id"] = body["r1_user_id"]
    if kind == "admin_reader":body["r1_user_id"] = pair["admin"].id
    if kind == "wrong_hash":body["expected_ct_sha256"] = "b"*64
    if kind == "no_ack":body["acknowledge_unverified"] = False
    if kind == "empty_protocol":body["protocol_version"] = " "
    assert client.post("/api/v1/review-studies",headers=pair["ah"],json=body).status_code in {409,422}
    assert db.scalar(select(func.count()).select_from(ReviewStudy)) == 0
    assert db.scalar(select(func.count()).select_from(ReviewAssignment)) == 0


@pytest.mark.parametrize("role", ["Clinician","Researcher","DataScientist"])
def test_only_admin_coordinator_can_assign(client, pair, account, role):
    _,headers=account(role)
    assert client.post("/api/v1/review-studies",headers=headers,json=pair["body"]).status_code == 403
    assert client.get("/api/v1/review-studies/source",headers=headers,params={"case_id":pair["body"]["case_id"]}).status_code == 403


def test_known_exposure_cannot_be_relabelled_blinded(client,pair,db):
    assert client.get(f"/api/v1/cases/{pair['body']['case_id']}/segmentations",headers=pair["h1"]).status_code == 200
    result=client.post("/api/v1/review-studies",headers=pair["ah"],json=pair["body"])
    assert result.status_code == 409 and "prior" in result.json()["detail"]
    assert db.scalar(select(func.count()).select_from(ReviewAssignment)) == 0


def test_private_note_revision_source_changes_and_no_release(client,pair):
    ids=assigned(client,pair);url=f"/api/v1/review-assignments/{ids['R1']}/draft"
    blank=client.get(url,headers=pair["h1"]).json()
    assert blank["exists"] is False and blank["revision"] == 0 and blank["notes"] == ""
    assert client.put(url,headers=pair["h1"],json=note()).status_code == 201
    assert client.put(url,headers=pair["h1"],json=note("revised",1)).json()["revision"] == 2
    assert client.put(url,headers=pair["h1"],json=note("stale",1)).status_code == 409
    data=client.get(url,headers=pair["h1"]).json()
    assert data["notes"] == "revised" and data["clinical_gate_authorized"] is data["training_release_authorized"] is False
    for flag in ["clinical_gate_authorized","training_release_authorized"]:
        body=note(revision=2);body[flag]=True
        assert client.put(url,headers=pair["h1"],json=body).status_code == 422
    pair["prepared"]["path"].write_bytes(b"changed synthetic CT")
    assert client.get(f"/api/v1/review-assignments/{ids['R1']}",headers=pair["h1"]).json()["source_current"] is False
    assert client.get(f"/api/v1/review-assignments/{ids['R1']}/source",headers=pair["h1"]).status_code == 409
    assert client.put(url,headers=pair["h1"],json=note("wrong source",2)).status_code == 409
    assert client.get(url,headers=pair["h1"]).json()["notes"] == "revised"


def test_escalating_assigned_role_does_not_bypass_isolation(client,pair,db):
    assigned(client,pair)
    db.execute(update(User).where(User.id == pair["r1"].id).values(role="Admin"));db.commit()
    assert client.get("/api/v1/admin/users",headers=pair["h1"]).status_code == 403
    assert client.get("/api/v1/cases",headers=pair["h1"]).status_code == 403
    assert client.post("/api/v1/review-studies",headers=pair["h1"],json=pair["body"]).status_code == 403


def test_assignment_and_notes_survive_logout_login(client,pair):
    ids=assigned(client,pair);url=f"/api/v1/review-assignments/{ids['R1']}/draft"
    assert client.put(url,headers=pair["h1"],json=note()).status_code == 201
    assert client.post("/api/v1/auth/logout",headers=pair["h1"]).status_code == 204
    assert client.get(url,headers=pair["h1"]).status_code == 401
    login=client.post("/api/v1/auth/login",json={"email":pair["r1"].email,"password":PASSWORD}).json()
    headers={"Authorization":"Bearer "+login["access_token"]}
    assert client.get(url,headers=headers).json()["revision"] == 1
    assert client.get("/api/v1/cases",headers=headers).status_code == 403


def test_postgres_two_note_writers_same_revision(client,pair,db,monkeypatch):
    if db.bind.dialect.name != "postgresql":pytest.skip("PostgreSQL concurrency")
    ids=assigned(client,pair);url=f"/api/v1/review-assignments/{ids['R1']}/draft"
    assert client.put(url,headers=pair["h1"],json=note()).status_code == 201
    original=service.note_for_save;barrier=Barrier(2,timeout=15);connections=[]
    def both(session,assignment_id):
        row=original(session,assignment_id);assert row.revision == 1
        connections.append(session.scalar(text("SELECT pg_backend_pid()")));barrier.wait();return row
    monkeypatch.setattr(service,"note_for_save",both)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda value:client.put(url,headers=pair["h1"],json=note(value,1)),["one","two"]))
    assert sorted(r.status_code for r in results) == [200,409] and len(set(connections)) == 2
    assert client.get(url,headers=pair["h1"]).json()["revision"] == 2


def test_0011_to_0012_preserves_existing_schema_and_binding_is_immutable(client,pair,db):
    db.rollback();cfg=Config("alembic.ini");command.downgrade(cfg,"0011_annotation_drafts")
    def counts():
        with engine.connect() as connection:
            return {name:connection.scalar(text(f"SELECT count(*) FROM {name}")) for name in ["users","patients","cases","segmentation_results","annotation_drafts","case_reviews"]}
    before=counts();command.upgrade(cfg,"0012_ct_review_assignments");assert counts() == before
    # Test 0012 bindings directly; the current API correctly refuses old schemas.
    from app.schemas.review_assignment import AssignReaders
    service.assign(db,pair['admin'],AssignReaders.model_validate(pair['body']))
    for cls,values in [(ReviewStudy,{"protocol_version":"changed"}),(ReviewAssignment,{"slot":"R2"})]:
        with pytest.raises(IntegrityError):db.execute(update(cls).values(**values));db.commit()
        db.rollback()
    with engine.connect() as connection:assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0012_ct_review_assignments"


def test_assignment_waits_for_inflight_ai_access_and_then_rejects_exposure(client,pair,db,monkeypatch):
    if db.bind.dialect.name != "postgresql":pytest.skip("PostgreSQL request-drain synchronization")
    from app.routers import segmentation
    entered,release=Event(),Event();original=segmentation.snapshot_source
    def paused(*args,**kwargs):
        entered.set();assert release.wait(10)
        return original(*args,**kwargs)
    monkeypatch.setattr(segmentation,"snapshot_source",paused)
    source=f"/api/v1/cases/{pair['body']['case_id']}/segmentations/{pair['prepared']['run_id']}/source"
    with ThreadPoolExecutor(max_workers=2) as pool:
        read=pool.submit(client.get,source,headers=pair["h1"])
        assert entered.wait(10)
        assignment=pool.submit(client.post,"/api/v1/review-studies",headers=pair["ah"],json=pair["body"])
        try:
            with pytest.raises(FutureTimeout):assignment.result(timeout=.3)
        finally:release.set()
        assert read.result(timeout=10).status_code == 200
        result=assignment.result(timeout=10)
    assert result.status_code == 409 and "prior" in result.json()["detail"]
    assert db.scalar(select(func.count()).select_from(ReviewAssignment)) == 0


def test_missing_expired_and_unauthorized_sessions_cannot_read_assignment(client,pair,account):
    from datetime import datetime,timedelta,timezone
    import jwt
    from app.core.config import settings
    ids=assigned(client,pair);url=f"/api/v1/review-assignments/{ids['R1']}"
    assert client.get(url).status_code == 401
    expired=jwt.encode(dict(sub=str(pair['r1'].id),role='Clinician',ver=0,iss=settings.JWT_ISSUER,
        aud=settings.JWT_AUDIENCE,iat=datetime.now(timezone.utc)-timedelta(hours=2),
        exp=datetime.now(timezone.utc)-timedelta(hours=1)),settings.SECRET_KEY.get_secret_value(),algorithm=settings.ALGORITHM)
    assert client.get(url,headers={'Authorization':'Bearer '+expired}).status_code == 401
    for role in ['Researcher','DataScientist']:
        _,headers=account(role)
        assert client.get(url,headers=headers).status_code == 403
        assert client.get(url+'/source',headers=headers).status_code == 403
        assert client.get(url+'/draft',headers=headers).status_code == 403


def test_other_case_draft_and_assignment_ids_are_not_accessible(client,pair,prepared):
    ids=assigned(client,pair)
    # Stage 2 drafts are prediction-exposed preparation, never a blind-review shortcut.
    assert client.get(prepared['url'],headers=pair['h1']).status_code == 403
    assert client.post(prepared['url'],headers=pair['h1'],json={'document':prepared['document']}).status_code == 403
    assert client.get(f"/api/v1/review-assignments/{uuid4()}",headers=pair['h1']).status_code == 404
    assert client.get(f"/api/v1/review-assignments/{ids['R2']}/draft",headers=pair['h1']).status_code == 404


@pytest.mark.parametrize('change',['clinical_release','training_release','owner','revision','inactive'])
def test_database_rejects_note_release_owner_revision_and_inactive_author(client,pair,db,change):
    ids=assigned(client,pair);url=f"/api/v1/review-assignments/{ids['R1']}/draft"
    assert client.put(url,headers=pair['h1'],json=note()).status_code == 201
    values=dict(notes='must not persist',revision=2)
    if change=='clinical_release':values['clinical_gate_authorized']=True
    if change=='training_release':values['training_release_authorized']=True
    if change=='owner':values['owner_id']=pair['r2'].id
    if change=='revision':values['revision']=1
    if change=='inactive':
        db.execute(update(User).where(User.id==pair['r1'].id).values(is_active=False));db.commit()
    with pytest.raises(IntegrityError):
        db.execute(update(ReviewNoteDraft).where(ReviewNoteDraft.assignment_id==ids['R1']).values(**values));db.commit()
    db.rollback();stored=db.get(ReviewNoteDraft,ids['R1'])
    assert stored.revision==1 and stored.notes=='Synthetic private preparation'
    assert stored.owner_id==pair['r1'].id and stored.clinical_gate_authorized is stored.training_release_authorized is False


def test_missing_review_schema_never_assumes_unassigned_access(client,pair,db):
    db.rollback();cfg=Config('alembic.ini');command.downgrade(cfg,'0011_annotation_drafts')
    try:
        response=client.get('/api/v1/cases',headers=pair['h1'])
        assert response.status_code==503
        assert 'Alembic migrations' in response.json()['detail']
    finally:command.upgrade(cfg,'head')


def test_failed_exposure_audit_prevents_legacy_endpoint_execution(client,pair,monkeypatch):
    from sqlalchemy.orm import Session
    from app.models.audit import AuditEvent
    original=Session.commit
    def failed_audit(self):
        if any(isinstance(row,AuditEvent) and row.action=='review.prior_workspace_access' for row in self.new):
            raise RuntimeError('Synthetic audit failure')
        return original(self)
    monkeypatch.setattr(Session,'commit',failed_audit)
    response=client.get('/api/v1/cases',headers=pair['h1'])
    assert response.status_code==503 and 'not started' in response.json()['detail']


def test_exposure_is_recorded_before_endpoint_execution(client,pair,monkeypatch):
    from app.models.audit import AuditEvent
    from app.routers import segmentation
    called=[];original=segmentation.current_result
    def checked(session,*args):
        with SessionLocal() as fresh:
            assert fresh.scalar(select(AuditEvent.id).where(AuditEvent.actor_id==pair['r1'].id,
                AuditEvent.action=='review.prior_workspace_access').limit(1)) is not None
        called.append(True);return original(session,*args)
    monkeypatch.setattr(segmentation,'current_result',checked)
    path=f"/api/v1/cases/{pair['body']['case_id']}/segmentations/{pair['prepared']['run_id']}/source"
    assert client.get(path,headers=pair['h1']).status_code==200 and called
    assert client.post('/api/v1/review-studies',headers=pair['ah'],json=pair['body']).status_code==409


def test_original_ct_download_honours_existing_tighter_file_limit(client,pair,monkeypatch):
    from app.core.config import settings
    ids=assigned(client,pair)
    monkeypatch.setattr(settings,'MAX_VOLUME_COMPRESSED_MB',0)
    response=client.get(f"/api/v1/review-assignments/{ids['R1']}/source",headers=pair['h1'])
    assert response.status_code==409
