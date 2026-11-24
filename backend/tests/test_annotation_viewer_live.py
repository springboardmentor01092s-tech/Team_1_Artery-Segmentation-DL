"""Opt-in UI+real API verification using disposable PostgreSQL and synthetic CT."""
import gzip
import os
from pathlib import Path
import shutil
import socket
import subprocess
from threading import Thread
import time

import httpx
import nibabel as nib
import numpy as np
import pytest
from sqlalchemy import select
import uvicorn

from app.main import app
from app.database.session import SessionLocal
from app.models.annotation_draft import AnnotationDraft
from app.models.segmentation import SegmentationResult
from conftest import PASSWORD
from test_annotation_drafts import prepared


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_ready(url, process=None):
    deadline = time.monotonic()+25
    while time.monotonic() < deadline:
        if process is not None and process.poll() is not None:
            raise RuntimeError("Disposable frontend exited before readiness")
        try:
            if httpx.get(url, timeout=1).status_code == 200:return
        except httpx.HTTPError:pass
        time.sleep(.05)
    raise RuntimeError("Disposable test server readiness timeout")


@pytest.mark.skipif(os.environ.get("VASCULAI_ANNOTATION_LIVE") != "1", reason="Opt-in actual-API browser test on disposable PostgreSQL only")
def test_actual_viewer_save_conflict_login_and_source_change(prepared, db):
    if db.bind.dialect.name != "postgresql":pytest.fail("Actual viewer test requires disposable PostgreSQL")
    node = shutil.which("node")
    if node is None:pytest.fail("Installed frontend Node dependencies required")
    artifacts = Path(os.environ["ANNOTATION_QA_ARTIFACT_DIR"])
    artifacts.mkdir(parents=True, exist_ok=True)
    frontend = Path(__file__).resolve().parents[2]/"frontend-react"
    run=db.get(SegmentationResult,prepared["run_id"])
    run.metadata_json={**run.metadata_json,"architecture":"synthetic-test-fixture-no-model-execution",
                       "experimental":True,"clinical_validation":False}
    db.commit()
    mask = nib.Nifti1Image(np.ones((5,7,9),dtype=np.uint8),np.eye(4));mask.header.set_xyzt_units("mm")
    (prepared["folder"]/"prediction_mask.nii.gz").write_bytes(gzip.compress(mask.to_bytes()))
    replacement = nib.Nifti1Image(np.ones((5,7,9),dtype=np.int16),np.eye(4));replacement.header.set_xyzt_units("mm")
    replacement_file = artifacts/"synthetic-replacement.nii.gz"
    replacement_file.write_bytes(gzip.compress(replacement.to_bytes()))
    api_port,web_port = free_port(),free_port()
    while web_port == api_port:web_port = free_port()
    server = uvicorn.Server(uvicorn.Config(app,host="127.0.0.1",port=api_port,log_level="error",access_log=False))
    thread = Thread(target=server.run,daemon=True);thread.start()
    frontend_process = None
    try:
        wait_ready(f"http://127.0.0.1:{api_port}/health/ready")
        environment = os.environ.copy()
        environment.update(PLAYWRIGHT_BASE_URL=f"http://127.0.0.1:{web_port}",
            PLAYWRIGHT_LIVE_API_URL=f"http://127.0.0.1:{api_port}",PLAYWRIGHT_ARTIFACT_DIR=str(artifacts),
            ANNOTATION_QA_EMAIL=prepared["owner"].email,ANNOTATION_QA_PASSWORD=PASSWORD,
            ANNOTATION_QA_CASE=str(prepared["case_id"]),ANNOTATION_QA_RUN=prepared["run_id"],
            ANNOTATION_QA_OWNER=str(prepared["owner"].id),ANNOTATION_QA_REPLACEMENT=str(replacement_file))
        with (artifacts/"vite.log").open("w",encoding="utf-8") as log:
            frontend_process = subprocess.Popen([node,"tests/e2e/start-server.mjs"],cwd=frontend,env=environment,
                stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
            wait_ready(environment["PLAYWRIGHT_BASE_URL"],frontend_process)
            result = subprocess.run([node,"tests/annotation-live-runner.mjs"],cwd=frontend,env=environment,
                capture_output=True,text=True,encoding="utf-8",errors="replace",timeout=150)
        output=(result.stdout+result.stderr).replace(PASSWORD,"[REDACTED_TEST_PASSWORD]")
        (artifacts/"browser.log").write_text(output,encoding="utf-8")
        assert result.returncode == 0, output[-2500:]
        with SessionLocal() as fresh:
            rows=fresh.scalars(select(AnnotationDraft)).all()
            assert len(rows)==1 and rows[0].revision==3
            assert rows[0].document["reviewer_reference"]=="explicitly resolved live revision"
            assert rows[0].clinical_gate_authorized is rows[0].training_release_authorized is False
    finally:
        if frontend_process is not None:
            frontend_process.terminate();frontend_process.wait(timeout=15)
        server.should_exit=True;thread.join(timeout=20)
        if thread.is_alive():raise RuntimeError("Disposable API did not stop gracefully")
