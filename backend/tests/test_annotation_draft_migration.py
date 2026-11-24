"""Migrate only the isolated synthetic test schema; never an application DB."""
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

from app.database.session import engine
from test_annotation_drafts import prepared  # shared synthetic fixture


def test_0010_to_0011_is_additive_and_preserves_existing_records(prepared, db):
    db.rollback()
    cfg = Config("alembic.ini")
    command.downgrade(cfg, "0010_case_reviews")
    def snapshot():
        with engine.connect() as connection:
            return {name: connection.execute(text(f"SELECT * FROM {name} ORDER BY id")).all()
                    for name in ("users", "patients", "cases", "volume_metadata", "segmentation_results", "case_reviews", "audit_events")}
    before = snapshot()
    command.upgrade(cfg, "0011_annotation_drafts")
    assert snapshot() == before
    schema = inspect(engine)
    assert len(schema.get_foreign_keys("annotation_drafts")) == 4
    assert {item["name"] for item in schema.get_indexes("annotation_drafts")} == {"ix_annotation_drafts_owner_id"}
    assert {item["name"] for item in schema.get_check_constraints("annotation_drafts")} == {
        "ck_annotation_draft_revision", "ck_annotation_draft_status", "ck_annotation_draft_no_release"}
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0011_annotation_drafts"
        assert connection.scalar(text("SELECT count(*) FROM annotation_drafts")) == 0
        if engine.dialect.name == "postgresql":
            assert connection.scalar(text("SELECT count(*) FROM pg_trigger WHERE tgrelid='annotation_drafts'::regclass AND NOT tgisinternal")) == 1
    command.downgrade(cfg, "0010_case_reviews")
    assert snapshot() == before
    command.upgrade(cfg, "head")
