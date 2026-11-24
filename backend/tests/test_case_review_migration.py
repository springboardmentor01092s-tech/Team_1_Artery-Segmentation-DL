from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

from app.database.session import engine
from test_segmentation_api import seed, fake_runtime


def test_additive_review_migration_preserves_populated_cases_runs_and_files(client, account, fake_runtime, db):
    case_id, headers = seed(client, account)
    assert client.post(f"/api/v1/cases/{case_id}/segmentations", headers=headers, json={}).status_code == 201
    db.rollback()
    # No reviews at this point; move only the synthetic test schema to its base.
    cfg = Config("alembic.ini")
    command.downgrade(cfg, "0009_evaluations")
    def snapshot():
        with engine.connect() as c:
            return {t:c.execute(text(f"SELECT * FROM {t} ORDER BY id")).all()
                    for t in ["users", "patients", "cases", "volume_metadata", "segmentation_results", "audit_events"]}
    before = snapshot()
    command.upgrade(cfg, "0010_case_reviews")
    assert snapshot() == before
    schema = inspect(engine)
    assert "case_reviews" in schema.get_table_names()
    assert {"uq_case_review_run"} <= {u["name"] for u in schema.get_unique_constraints("case_reviews")}
    assert any(f["constrained_columns"] == ["segmentation_result_id", "case_id"] for f in schema.get_foreign_keys("case_reviews"))
    with engine.connect() as c:
        assert c.scalar(text("SELECT version_num FROM alembic_version")) == "0010_case_reviews"
        assert c.scalar(text("SELECT count(*) FROM case_reviews")) == 0
