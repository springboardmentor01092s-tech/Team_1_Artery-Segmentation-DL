"""Test-harness cleanup never weakens runtime enforcement or targets real files."""
from types import SimpleNamespace
import pytest
from sqlalchemy.exc import IntegrityError
from app.models import Case
import conftest


def test_sqlite_fallback_restores_foreign_keys_before_test_operations(db):
    if db.bind.dialect.name!='sqlite':pytest.skip('SQLite-only isolated fallback assertion')
    assert db.connection().exec_driver_sql('PRAGMA foreign_keys').scalar()==1
    db.add(Case(patient_id=2147483647,case_code='SYNTHETIC-INVALID-FK'))
    with pytest.raises(IntegrityError,match='FOREIGN KEY'):db.flush()
    db.rollback()


def test_cleanup_refuses_a_file_database_before_connect_or_destructive_operations(monkeypatch):
    def forbidden():pytest.fail('Cleanup must refuse before connecting')
    fake=SimpleNamespace(dialect=SimpleNamespace(name='sqlite'),url=SimpleNamespace(database='artery_db'),connect=forbidden)
    monkeypatch.setattr(conftest,'engine',fake)
    with pytest.raises(RuntimeError,match='isolated in-memory'):conftest.clear_database()
