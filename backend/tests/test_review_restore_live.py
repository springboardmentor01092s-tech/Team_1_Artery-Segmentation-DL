"""Opt-in synthetic schema backup/restore. Never an application backup tool."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import re
from uuid import uuid4
import pytest
from sqlalchemy import create_engine, inspect, text
from app.database.session import engine
from conftest import SCHEMA
from test_annotation_drafts import prepared
from test_review_assignments import pair
from test_review_adjudications import third, allocate, blank


@pytest.mark.skipif(os.environ.get('VASCULAI_RESTORE_LIVE') != '1', reason='Explicit disposable QA backup/restore opt-in')
def test_current_review_schema_custom_dump_restores_into_new_disposable_database(client, pair, third, db):
    container = 'vascuai-closeout-qa-6261baf3c25b'
    if (engine.dialect.name != 'postgresql' or engine.url.host != '127.0.0.1' or engine.url.port != 50780
            or not engine.url.database.startswith('vascuai_sprint_test_') or not SCHEMA.startswith('vascuai_test_')):
        pytest.fail('Only the named isolated QA instance/schema is permitted')
    info = json.loads(subprocess.run(['docker', 'inspect', container], capture_output=True, check=True).stdout)[0]
    assert info['Id'] == '92a285f5ce936e6cdba70466541a83d6dab0f658af614cbb6da576b0b371bb9c'
    assert info['Image'] == 'sha256:74935e72241653ca55e0414067e6d8763aceb8a810eb51b452253ec3dcfc4336'
    assert info['State']['Running']
    # Populate all new review stages using synthetic-only account/credential/CT
    # fixtures before the snapshot. Production credentials/data are never read.
    key = allocate(client, pair, third); doc = blank(client, third, key)
    saved = client.put(f'/api/v1/review-adjudications/{key}/draft', headers=third['headers'], json=dict(document=doc, expected_revision=0))
    assert saved.status_code == 200
    frozen = client.post(f'/api/v1/review-adjudications/{key}/submit', headers=third['headers'],
        json=dict(expected_revision=1, expected_document_sha256=saved.json()['document_sha256'], acknowledge_unverified=True))
    assert frozen.status_code == 201
    db.rollback()
    names = inspect(engine).get_table_names(schema=SCHEMA)
    def fingerprint(target, definitions):
        result = {}
        with target.connect() as connection:
            for name in sorted(names):
                rows = [dict(row) for row in connection.execute(text(f'SELECT * FROM "{SCHEMA}"."{name}"')).mappings()]
                canonical = sorted(json.dumps(row, sort_keys=True, default=str, separators=(',', ':')) for row in rows)
                result[name] = dict(rows=len(rows), sha256=hashlib.sha256('\n'.join(canonical).encode()).hexdigest())
            objects = {}
            queries = {
                'indexes': "SELECT indexname,indexdef FROM pg_indexes WHERE schemaname=:schema ORDER BY indexname",
                'constraints': "SELECT c.relname,x.conname,pg_get_constraintdef(x.oid) FROM pg_constraint x JOIN pg_class c ON c.oid=x.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=:schema ORDER BY c.relname,x.conname",
                'triggers': "SELECT c.relname,t.tgname,pg_get_triggerdef(t.oid) FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=:schema AND NOT t.tgisinternal ORDER BY c.relname,t.tgname",
                'functions': "SELECT p.proname,pg_get_functiondef(p.oid) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname=:schema ORDER BY p.proname",
            }
            for name, sql in queries.items():
                rows = [list(r) for r in connection.execute(text(sql), {'schema':SCHEMA})]
                definitions[name] = rows
                comparable = rows
                if name == 'constraints':
                    # PostgreSQL 18 reparses VARCHAR[]->TEXT[] as per-element
                    # casts during pg_restore. Normalize only these five known
                    # literal-enumeration checks, retaining raw DDL evidence.
                    known = {'ck_review_assignment_slot','ck_case_review_outcome','ck_users_role',
                             'ck_stenosis_job_failure_code','ck_stenosis_job_status'}
                    pattern = r"\(ARRAY\[((?:'[^']*'::character varying)(?:, '[^']*'::character varying)*)\]\)::text\[\]"
                    def literal_casts(match):
                        return 'ARRAY['+', '.join('('+part+')::text' for part in match[1].split(', '))+']'
                    comparable = [[*row[:2], re.sub(pattern, literal_casts, row[2]) if row[1] in known else row[2]] for row in rows]
                objects[name] = dict(count=len(rows), sha256=hashlib.sha256(json.dumps(comparable, sort_keys=True).encode()).hexdigest())
            sequences = {}
            for name in inspect(target).get_sequence_names(schema=SCHEMA):
                row = connection.execute(text(f'SELECT last_value,is_called FROM "{SCHEMA}"."{name}"')).one()
                sequences[name] = list(row)
            return dict(tables=result, schema_objects=objects, sequences=sequences,
                revision=connection.scalar(text(f'SELECT version_num FROM "{SCHEMA}".alembic_version')))
    original_definitions = {}; original = fingerprint(engine, original_definitions)
    assert original['revision'] == '0015_review_adjudication'
    folder = Path(os.environ['ANNOTATION_QA_ARTIFACT_DIR']) / 'synthetic-restore'
    folder.mkdir(parents=True, exist_ok=False)
    dump = subprocess.run(['docker', 'exec', container, 'pg_dump', '-U', engine.url.username, '-d', engine.url.database,
        '--format=custom', '--no-owner', '--no-privileges', '--schema='+SCHEMA], capture_output=True, check=True).stdout
    archive = folder/'synthetic-review-schema.dump'
    with archive.open('xb') as stream: stream.write(dump)
    listed = subprocess.run(['docker', 'exec', '-i', container, 'pg_restore', '--list'], input=dump, capture_output=True)
    assert listed.returncode == 0 and b'adjudication_versions' in listed.stdout
    destination = 'vascuai_sprint_restore_' + uuid4().hex[:16]
    query = subprocess.run(['docker', 'exec', container, 'psql', '-U', engine.url.username, '-d', 'postgres', '-Atc',
        f"SELECT count(*) FROM pg_database WHERE datname='{destination}'"], capture_output=True, check=True)
    assert query.stdout.strip() == b'0'
    subprocess.run(['docker', 'exec', container, 'createdb', '-U', engine.url.username, '--template=template0', destination], capture_output=True, check=True)
    restored = subprocess.run(['docker', 'exec', '-i', container, 'pg_restore', '-U', engine.url.username, '-d', destination,
        '--exit-on-error', '--no-owner', '--no-privileges'], input=dump, capture_output=True)
    assert restored.returncode == 0, 'Disposable restore failed; private log must be reviewed locally'
    target = create_engine(engine.url.set(database=destination))
    try:
        restored_definitions = {}; restored_fingerprint = fingerprint(target, restored_definitions)
        with (folder/'SCHEMA-COMPARISON.json').open('x', encoding='utf-8') as stream:
            json.dump(dict(original=original, restored=restored_fingerprint, original_definitions=original_definitions,
                restored_definitions=restored_definitions, retained_disposable_database=destination), stream, indent=2)
        assert restored_fingerprint == original
    finally: target.dispose()
    report = dict(status='PASS', synthetic_only=True, archive=archive.name, bytes=len(dump),
        sha256=hashlib.sha256(dump).hexdigest(), pg_restore_list_exit=listed.returncode,
        restore_exit=restored.returncode, retained_disposable_database=destination, evidence=original,
        application_databases_accessed=False, staging_backup_verified=False,
        limitations=['Schema-only synthetic QA dump; not a staging backup', 'No real private storage, ACL or xattr restore was exercised',
            'Five PostgreSQL VARCHAR[]/TEXT[] enumeration checks have equivalent deparser cast forms; raw DDL retained, narrow cast normalization used'])
    with (folder/'RESTORE-RESULT.json').open('x', encoding='utf-8') as stream: json.dump(report, stream, indent=2)
