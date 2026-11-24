"""Owner-bound mutable preparation drafts; no existing data transformation.

Revision ID: 0011_annotation_drafts
Revises: 0010_case_reviews
Downgrade permanently deletes private drafts, not cases, reviews or evaluations.
No submitted/clinical record type is introduced by this migration.
"""
from alembic import op
import sqlalchemy as sa

revision = "0011_annotation_drafts"
down_revision = "0010_case_reviews"
branch_labels = None
depends_on = None

FLAGS = ("reader_independence_verified", "clinical_validation", "training_eligible",
         "quantitative_gate_authorized", "clinical_gate_authorized", "training_release_authorized")
IMMUTABLE = ("id", "case_id", "patient_id", "owner_id", "segmentation_result_id", "source_volume_path",
             "source_json", "geometry_sha256", "segmentation_provenance", "created_at", "status")


def upgrade():
    op.create_table("annotation_drafts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("case_id", sa.Integer(), sa.ForeignKey("cases.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("patient_id", sa.Integer(), sa.ForeignKey("patients.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("segmentation_result_id", sa.String(36), nullable=False),
        sa.Column("source_volume_path", sa.String(500), nullable=False),
        sa.Column("source_json", sa.JSON(), nullable=False),
        sa.Column("geometry_sha256", sa.String(64), nullable=False),
        sa.Column("segmentation_provenance", sa.JSON(), nullable=False),
        sa.Column("document", sa.JSON(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(40), nullable=False, server_default="unverified_server_draft"),
        sa.Column("clinical_gate_authorized", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("training_release_authorized", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["segmentation_result_id", "case_id"],
                                ["segmentation_results.id", "segmentation_results.case_id"], ondelete="RESTRICT"),
        sa.CheckConstraint("revision > 0", name="ck_annotation_draft_revision"),
        sa.CheckConstraint("status = 'unverified_server_draft'", name="ck_annotation_draft_status"),
        sa.CheckConstraint("NOT clinical_gate_authorized AND NOT training_release_authorized", name="ck_annotation_draft_no_release"),
    )
    op.create_index("ix_annotation_drafts_owner_id", "annotation_drafts", ["owner_id"])
    if op.get_bind().dialect.name == "postgresql":
        comparisons = " OR ".join(f"NEW.{key}::text IS DISTINCT FROM OLD.{key}::text" for key in IMMUTABLE)
        flags = " OR ".join(f"NEW.document::jsonb->'{key}' IS DISTINCT FROM 'false'::jsonb" for key in FLAGS)
        op.execute(f"""CREATE OR REPLACE FUNCTION annotation_draft_guard() RETURNS trigger AS $$
        BEGIN
          PERFORM id FROM users WHERE id=CASE WHEN TG_OP='DELETE' THEN OLD.owner_id ELSE NEW.owner_id END
            AND is_active AND role IN ('Clinician','Admin') FOR SHARE;
          IF NOT FOUND THEN RAISE EXCEPTION 'Draft author unavailable' USING ERRCODE='23514'; END IF;
          IF TG_OP='DELETE' THEN RETURN OLD; END IF;
          IF NOT EXISTS(SELECT 1 FROM cases WHERE id=NEW.case_id AND patient_id=NEW.patient_id) THEN
            RAISE EXCEPTION 'Draft case binding invalid' USING ERRCODE='23514'; END IF;
          IF NEW.document::jsonb->'source' IS DISTINCT FROM NEW.source_json::jsonb
             OR NEW.source_json::jsonb->>'case_id' IS DISTINCT FROM NEW.case_id::text
             OR NEW.source_json::jsonb->>'segmentation_result_id' IS DISTINCT FROM NEW.segmentation_result_id
             OR NEW.document::jsonb->>'status' IS DISTINCT FROM 'unverified_local_draft'
             OR {flags} THEN RAISE EXCEPTION 'Draft payload invalid' USING ERRCODE='23514'; END IF;
          IF TG_OP='INSERT' AND NEW.revision<>1 THEN
            RAISE EXCEPTION 'Draft revision invalid' USING ERRCODE='23514'; END IF;
          IF TG_OP='UPDATE' AND (({comparisons}) OR NEW.revision<>OLD.revision+1) THEN
            RAISE EXCEPTION 'Draft binding or revision immutable' USING ERRCODE='23514'; END IF;
          RETURN NEW;
        END; $$ LANGUAGE plpgsql""")
        op.execute("CREATE TRIGGER annotation_draft_guard BEFORE INSERT OR UPDATE OR DELETE ON annotation_drafts FOR EACH ROW EXECUTE FUNCTION annotation_draft_guard()")
    else:
        flags = " OR ".join(f"json_type(NEW.document,'$.{key}') IS NOT 'false'" for key in FLAGS)
        binding = " OR ".join(f"NEW.{key} IS NOT OLD.{key}" for key in IMMUTABLE)
        def source_tree(expression):
            # JSON numeric 1 and 1.0 describe the same native geometry. Compare
            # structure/leaves, not serialization order or numeric spelling.
            return f"""SELECT fullkey, CASE WHEN type IN ('integer','real') THEN 'number' ELSE type END,
                CASE WHEN type IN ('array','object') THEN NULL ELSE atom END FROM json_tree({expression})"""
        client_source = source_tree("json_extract(NEW.document,'$.source')")
        stored_source = source_tree("NEW.source_json")
        mismatch = f"EXISTS({client_source} EXCEPT {stored_source}) OR EXISTS({stored_source} EXCEPT {client_source})"
        for action in ("INSERT", "UPDATE", "DELETE"):
            row = "OLD" if action == "DELETE" else "NEW"
            op.execute(f"""CREATE TRIGGER annotation_draft_{action.lower()} BEFORE {action} ON annotation_drafts BEGIN
              SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM users WHERE id={row}.owner_id AND is_active=1
                AND role IN ('Clinician','Admin')) THEN RAISE(ABORT,'Draft author unavailable') END;
              {'' if action == 'DELETE' else f'''SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM cases WHERE id=NEW.case_id AND patient_id=NEW.patient_id)
                OR {mismatch}
                OR json_extract(NEW.source_json,'$.case_id') IS NOT NEW.case_id
                OR json_extract(NEW.source_json,'$.segmentation_result_id') IS NOT NEW.segmentation_result_id
                OR json_extract(NEW.document,'$.status') IS NOT 'unverified_local_draft' OR {flags}
                THEN RAISE(ABORT,'Draft payload invalid') END;'''}
              {"SELECT CASE WHEN NEW.revision<>1 THEN RAISE(ABORT,'Draft revision invalid') END;" if action == 'INSERT' else ''}
              {f"SELECT CASE WHEN ({binding}) OR NEW.revision<>OLD.revision+1 THEN RAISE(ABORT,'Draft binding or revision immutable') END;" if action == 'UPDATE' else ''}
            END""")


def downgrade():
    op.drop_table("annotation_drafts")
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP FUNCTION annotation_draft_guard()")
