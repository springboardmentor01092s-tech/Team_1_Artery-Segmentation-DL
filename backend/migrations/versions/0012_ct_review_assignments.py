"""Original-CT R1/R2 account separation and private mutable notes.

No submitted review or adjudication record is created. Downgrade deletes all
assignment metadata and private notes; it is destructive and not routine rollback.
"""
from alembic import op
import sqlalchemy as sa

revision = "0012_ct_review_assignments"
down_revision = "0011_annotation_drafts"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("review_studies",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("case_id", sa.Integer(), sa.ForeignKey("cases.id", ondelete="RESTRICT"), nullable=False, unique=True),
        sa.Column("patient_id", sa.Integer(), sa.ForeignKey("patients.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("coordinator_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("protocol_version", sa.String(128), nullable=False),
        sa.Column("source_volume_path", sa.String(500), nullable=False),
        sa.Column("source_json", sa.JSON(), nullable=False),
        sa.Column("geometry_sha256", sa.String(64), nullable=False),
        sa.Column("clinical_gate_authorized", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("training_release_authorized", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("NOT clinical_gate_authorized AND NOT training_release_authorized", name="ck_review_study_no_release"))
    op.create_table("review_assignments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("study_id", sa.String(36), sa.ForeignKey("review_studies.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("reviewer_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("slot", sa.String(2), nullable=False),
        sa.UniqueConstraint("study_id", "slot", name="uq_review_assignment_slot"),
        sa.UniqueConstraint("study_id", "reviewer_id", name="uq_review_assignment_distinct_reader"),
        sa.UniqueConstraint("id", "reviewer_id", name="uq_review_assignment_owner"),
        sa.CheckConstraint("slot IN ('R1','R2')", name="ck_review_assignment_slot"))
    op.create_index("ix_review_assignments_reviewer_id", "review_assignments", ["reviewer_id"])
    op.create_table("review_note_drafts",
        sa.Column("assignment_id", sa.String(36), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("clinical_gate_authorized", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("training_release_authorized", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["assignment_id", "owner_id"], ["review_assignments.id", "review_assignments.reviewer_id"], ondelete="RESTRICT"),
        sa.CheckConstraint("revision > 0", name="ck_review_note_revision"),
        sa.CheckConstraint("NOT clinical_gate_authorized AND NOT training_release_authorized", name="ck_review_note_no_release"))
    if op.get_bind().dialect.name == "postgresql":
        op.execute("""CREATE OR REPLACE FUNCTION ct_review_binding_guard() RETURNS trigger AS $$ BEGIN
          IF TG_OP <> 'INSERT' THEN RAISE EXCEPTION 'Review assignment binding is immutable' USING ERRCODE='23514'; END IF;
          IF TG_TABLE_NAME='review_studies' THEN
            PERFORM id FROM users WHERE id=NEW.coordinator_id AND is_active AND role='Admin' FOR SHARE;
            IF NOT FOUND OR NOT EXISTS(SELECT 1 FROM cases WHERE id=NEW.case_id AND patient_id=NEW.patient_id) THEN
              RAISE EXCEPTION 'Review coordinator or case invalid' USING ERRCODE='23514'; END IF;
          ELSE
            PERFORM id FROM users WHERE id=NEW.reviewer_id AND is_active AND role='Clinician' FOR SHARE;
            IF NOT FOUND THEN RAISE EXCEPTION 'Review reader invalid' USING ERRCODE='23514'; END IF;
          END IF; RETURN NEW;
        END; $$ LANGUAGE plpgsql""")
        for table in ("review_studies", "review_assignments"):
            op.execute(f"CREATE TRIGGER {table}_guard BEFORE INSERT OR UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION ct_review_binding_guard()")
        op.execute("""CREATE OR REPLACE FUNCTION ct_review_note_guard() RETURNS trigger AS $$ BEGIN
          IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Review note deletion is unavailable' USING ERRCODE='23514'; END IF;
          PERFORM id FROM users WHERE id=NEW.owner_id AND is_active AND role IN ('Clinician','Admin') FOR SHARE;
          IF NOT FOUND OR length(NEW.notes)>4000 THEN RAISE EXCEPTION 'Review note author or content invalid' USING ERRCODE='23514'; END IF;
          IF TG_OP='INSERT' AND NEW.revision<>1 OR TG_OP='UPDATE' AND
            (NEW.assignment_id<>OLD.assignment_id OR NEW.owner_id<>OLD.owner_id OR NEW.revision<>OLD.revision+1) THEN
            RAISE EXCEPTION 'Review note revision invalid' USING ERRCODE='23514'; END IF;
          RETURN NEW;
        END; $$ LANGUAGE plpgsql""")
        op.execute("CREATE TRIGGER review_note_guard BEFORE INSERT OR UPDATE OR DELETE ON review_note_drafts FOR EACH ROW EXECUTE FUNCTION ct_review_note_guard()")
    else:
        for table in ("review_studies", "review_assignments"):
            for action in ("UPDATE", "DELETE"):
                op.execute(f"CREATE TRIGGER {table}_{action.lower()} BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT,'Review assignment binding is immutable'); END")
        op.execute("""CREATE TRIGGER review_study_insert BEFORE INSERT ON review_studies BEGIN
          SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM users WHERE id=NEW.coordinator_id AND is_active=1 AND role='Admin')
          OR NOT EXISTS(SELECT 1 FROM cases WHERE id=NEW.case_id AND patient_id=NEW.patient_id)
          THEN RAISE(ABORT,'Review coordinator or case invalid') END; END""")
        op.execute("""CREATE TRIGGER review_assignment_insert BEFORE INSERT ON review_assignments BEGIN
          SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM users WHERE id=NEW.reviewer_id AND is_active=1 AND role='Clinician')
          THEN RAISE(ABORT,'Review reader invalid') END; END""")
        for action in ("INSERT", "UPDATE"):
            revision = "NEW.revision<>1" if action == "INSERT" else "NEW.assignment_id<>OLD.assignment_id OR NEW.owner_id<>OLD.owner_id OR NEW.revision<>OLD.revision+1"
            op.execute(f"""CREATE TRIGGER review_note_{action.lower()} BEFORE {action} ON review_note_drafts BEGIN
              SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM users WHERE id=NEW.owner_id AND is_active=1 AND role IN ('Clinician','Admin'))
              OR length(NEW.notes)>4000 OR ({revision}) THEN RAISE(ABORT,'Review note author or revision invalid') END; END""")
        op.execute("CREATE TRIGGER review_note_delete BEFORE DELETE ON review_note_drafts BEGIN SELECT RAISE(ABORT,'Review note deletion is unavailable'); END")


def downgrade():
    op.drop_table("review_note_drafts")
    op.drop_table("review_assignments")
    op.drop_table("review_studies")
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP FUNCTION ct_review_note_guard()")
        op.execute("DROP FUNCTION ct_review_binding_guard()")
