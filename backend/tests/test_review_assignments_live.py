"""Opt-in real HTTP/browser CT-review workflow; synthetic disposable PG only."""
import os
from pathlib import Path
import shutil
import subprocess
from threading import Thread
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select
import uvicorn

from app.main import app
from app.models.review_assignment import ReviewAssignment, ReviewNoteDraft
from app.models.review_submission import IndependentReviewSubmission
from app.models.review_adjudication import ReviewerCredential, AdjudicationVersion
from conftest import PASSWORD
from test_annotation_viewer_live import free_port, wait_ready
from test_annotation_drafts import prepared
from test_review_assignments import pair


@pytest.mark.skipif(os.environ.get('VASCULAI_REVIEW_LIVE')!='1',reason='Opt-in actual API on disposable PostgreSQL only')
def test_actual_coordinator_and_two_ct_only_readers(pair,db,account):
    if db.bind.dialect.name!='postgresql':pytest.fail('Disposable PostgreSQL required')
    node=shutil.which('node')
    if node is None:pytest.fail('Installed Node/browser dependencies required')
    artifacts=Path(os.environ['ANNOTATION_QA_ARTIFACT_DIR'])/'ct-review';artifacts.mkdir(parents=True,exist_ok=True)
    frontend=Path(__file__).resolve().parents[2]/'frontend-react'
    api_port,web_port=free_port(),free_port()
    third, _ = account('Clinician'); now = datetime.now(timezone.utc)
    credential = ReviewerCredential(id=str(uuid4()), reviewer_id=third.id, verified_by=pair['admin'].id,
        evidence_reference='SYNTHETIC QA ONLY - NOT CLINICAL QUALIFICATION', evidence_sha256='a'*64,
        scope='coronary-cta-lesion-adjudication', verified_at=now-timedelta(days=1), valid_until=now+timedelta(days=1), revoked=False)
    db.add(credential); db.commit()
    while web_port==api_port:web_port=free_port()
    server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=api_port,log_level='error',access_log=False))
    thread=Thread(target=server.run,daemon=True);thread.start();process=None
    try:
        wait_ready(f'http://127.0.0.1:{api_port}/health/ready')
        env=os.environ.copy();env.update(PLAYWRIGHT_BASE_URL=f'http://127.0.0.1:{web_port}',
            PLAYWRIGHT_LIVE_API_URL=f'http://127.0.0.1:{api_port}',PLAYWRIGHT_ARTIFACT_DIR=str(artifacts),
            REVIEW_QA_ADMIN=pair['admin'].email,REVIEW_QA_R1=pair['r1'].email,REVIEW_QA_R2=pair['r2'].email,
            REVIEW_QA_PASSWORD=PASSWORD,REVIEW_QA_CASE=str(pair['body']['case_id']),
            REVIEW_QA_R1_ID=str(pair['r1'].id),REVIEW_QA_R2_ID=str(pair['r2'].id),
            REVIEW_QA_R3=third.email, REVIEW_QA_R3_ID=str(third.id), REVIEW_QA_CREDENTIAL=credential.id,
            REVIEW_QA_HASH=pair['body']['expected_ct_sha256'])
        with (artifacts/'vite.log').open('w',encoding='utf-8') as log:
            process=subprocess.Popen([node,'tests/e2e/start-server.mjs'],cwd=frontend,env=env,stdout=log,
                stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            wait_ready(env['PLAYWRIGHT_BASE_URL'],process)
            result=subprocess.run([node,'tests/review-assignments-live-runner.mjs'],cwd=frontend,env=env,
                capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=180)
        output=(result.stdout+result.stderr).replace(PASSWORD,'[REDACTED_TEST_PASSWORD]')
        (artifacts/'browser.log').write_text(output,encoding='utf-8')
        assert result.returncode==0,output[-2500:]
        db.expire_all();rows=db.scalars(select(ReviewAssignment)).all();notes=db.scalars(select(ReviewNoteDraft)).all()
        assert len(rows)==2 and len(notes)==2
        assert {n.owner_id for n in notes}=={pair['r1'].id,pair['r2'].id}
        assert all(n.clinical_gate_authorized is n.training_release_authorized is False for n in notes)
        submissions=db.scalars(select(IndependentReviewSubmission)).all()
        assert len(submissions)==2
        assert all(v.clinical_gate_authorized is v.training_release_authorized is False for v in submissions)
        adjudications=db.scalars(select(AdjudicationVersion).order_by(AdjudicationVersion.revision)).all()
        assert len(adjudications)==2 and adjudications[1].final is True
        assert adjudications[1].previous_sha256==adjudications[0].record_sha256
        assert all(v.clinical_gate_authorized is v.training_release_authorized is False for v in adjudications)
    finally:
        if process is not None:process.terminate();process.wait(timeout=15)
        server.should_exit=True;thread.join(timeout=20)
        if thread.is_alive():raise RuntimeError('Disposable API did not stop gracefully')
