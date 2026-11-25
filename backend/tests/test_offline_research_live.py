"""Opt-in actual HTTP/browser verification; disposable PostgreSQL + synthetic files."""
import os
from pathlib import Path
import shutil
import subprocess
from threading import Thread
import pytest
import uvicorn
from app.main import app
from conftest import PASSWORD
from test_annotation_viewer_live import free_port,wait_ready
from test_offline_research_api import evidence


@pytest.mark.skipif(os.environ.get('VASCULAI_OFFLINE_LIVE')!='1',reason='Opt-in disposable actual API only')
@pytest.mark.parametrize('evidence',['small','native'],indirect=True)
def test_actual_source_bound_offline_browser(evidence,db):
    if db.bind.dialect.name!='postgresql':pytest.fail('Disposable PostgreSQL required')
    frontend=Path(__file__).resolve().parents[2]/'frontend-react'
    artifacts=Path(os.environ['ANNOTATION_QA_ARTIFACT_DIR'])/('offline-research-native' if evidence['native'] else 'offline-research');artifacts.mkdir(parents=True,exist_ok=False)
    node=shutil.which('node');assert node
    api_port,web_port=free_port(),free_port()
    while api_port==web_port:web_port=free_port()
    server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=api_port,log_level='error',access_log=False))
    thread=Thread(target=server.run,daemon=True);thread.start();process=None
    try:
        wait_ready(f'http://127.0.0.1:{api_port}/health/ready')
        import json
        packet=artifacts/'synthetic-evidence.json';packet.write_text(json.dumps(evidence['envelope']),encoding='utf-8')
        env=os.environ.copy();env.update(PLAYWRIGHT_BASE_URL=f'http://127.0.0.1:{web_port}',PLAYWRIGHT_LIVE_API_URL=f'http://127.0.0.1:{api_port}',
            PLAYWRIGHT_ARTIFACT_DIR=str(artifacts),OFFLINE_QA_EMAIL=evidence['owner'].email,OFFLINE_QA_PASSWORD=PASSWORD,
            OFFLINE_QA_CASE=str(evidence['case_id']),OFFLINE_QA_EVIDENCE=str(packet),
            OFFLINE_QA_EXPECTED_RAS='5.20, 20.40, 80.00' if evidence['native'] else '0.00, 0.00, 7.00')
        with (artifacts/'vite.log').open('w',encoding='utf-8') as log:
            process=subprocess.Popen([node,'tests/e2e/start-server.mjs'],cwd=frontend,env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            wait_ready(env['PLAYWRIGHT_BASE_URL'],process)
            result=subprocess.run([node,'tests/offline-research-live-runner.mjs'],cwd=frontend,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=180)
        output=(result.stdout+result.stderr).replace(PASSWORD,'[REDACTED]');(artifacts/'browser.log').write_text(output,encoding='utf-8')
        assert result.returncode==0,output[-2500:]
    finally:
        if process is not None:process.terminate();process.wait(timeout=15)
        server.should_exit=True;thread.join(timeout=20)
        if thread.is_alive():raise RuntimeError('Disposable API did not stop gracefully')
