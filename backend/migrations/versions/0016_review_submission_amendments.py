"""Append-only addenda for immutable independent reviews.

Original submissions and their adjudication parent hashes remain unchanged.
Downgrade drops amendment evidence and is intentionally destructive.
"""
from alembic import op
import sqlalchemy as sa

revision = '0016_review_amendments'
down_revision = '0015_review_adjudication'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'review_submission_amendments',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('assignment_id', sa.String(36), nullable=False),
        sa.Column('submission_id', sa.String(36), sa.ForeignKey('independent_review_submissions.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('owner_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('previous_id', sa.String(36), sa.ForeignKey('review_submission_amendments.id', ondelete='RESTRICT')),
        sa.Column('previous_sha256', sa.String(64)),
        sa.Column('parent_submission_sha256', sa.String(64), nullable=False),
        sa.Column('document_sha256', sa.String(64), nullable=False),
        sa.Column('record_sha256', sa.String(64), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('clinical_gate_authorized', sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column('training_release_authorized', sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['assignment_id', 'owner_id'], ['review_assignments.id', 'review_assignments.reviewer_id'], ondelete='RESTRICT'),
        sa.UniqueConstraint('assignment_id', 'revision', name='uq_review_amendment_revision'),
        sa.CheckConstraint('revision > 0', name='ck_review_amendment_revision'),
        sa.CheckConstraint('NOT clinical_gate_authorized AND NOT training_release_authorized', name='ck_review_amendment_no_release'),
    )
    op.create_index('ix_review_submission_amendments_assignment_id', 'review_submission_amendments', ['assignment_id'])

    if op.get_bind().dialect.name == 'postgresql':
        op.execute("""CREATE OR REPLACE FUNCTION review_submission_amendment_guard() RETURNS trigger AS $$
          DECLARE parent_hash text; parent_assignment text; parent_owner integer; latest_id text; latest_hash text; latest_revision integer;
          BEGIN
            IF TG_OP <> 'INSERT' THEN RAISE EXCEPTION 'Review amendments are append-only' USING ERRCODE='23514'; END IF;
            SELECT record_sha256, assignment_id, owner_id INTO parent_hash, parent_assignment, parent_owner
              FROM independent_review_submissions WHERE id=NEW.submission_id FOR SHARE;
            IF NOT FOUND OR parent_assignment IS DISTINCT FROM NEW.assignment_id OR parent_owner IS DISTINCT FROM NEW.owner_id
              OR parent_hash IS DISTINCT FROM NEW.parent_submission_sha256 THEN
              RAISE EXCEPTION 'Amendment parent binding invalid' USING ERRCODE='23514'; END IF;
            IF EXISTS(SELECT 1 FROM review_assignments a JOIN adjudication_assignments j ON j.study_id=a.study_id
                      WHERE a.id=NEW.assignment_id) THEN
              RAISE EXCEPTION 'Amendments close when adjudication is assigned' USING ERRCODE='23514'; END IF;
            SELECT id, record_sha256, revision INTO latest_id, latest_hash, latest_revision
              FROM review_submission_amendments WHERE assignment_id=NEW.assignment_id ORDER BY revision DESC LIMIT 1 FOR UPDATE;
            IF latest_id IS NULL THEN
              IF NEW.revision<>1 OR NEW.previous_id IS NOT NULL OR NEW.previous_sha256 IS NOT NULL THEN
                RAISE EXCEPTION 'Invalid initial amendment revision' USING ERRCODE='23514'; END IF;
            ELSIF NEW.revision<>latest_revision+1 OR NEW.previous_id IS DISTINCT FROM latest_id OR NEW.previous_sha256 IS DISTINCT FROM latest_hash THEN
              RAISE EXCEPTION 'Amendment revision is stale' USING ERRCODE='23514'; END IF;
            IF NEW.payload::jsonb->'clinical_gate_authorized' IS DISTINCT FROM 'false'::jsonb
              OR NEW.payload::jsonb->'training_release_authorized' IS DISTINCT FROM 'false'::jsonb
              OR NEW.payload->>'assignment_id' IS DISTINCT FROM NEW.assignment_id
              OR NEW.payload->>'reviewer_id' IS DISTINCT FROM NEW.owner_id::text
              OR NEW.payload->>'parent_submission_sha256' IS DISTINCT FROM NEW.parent_submission_sha256
              OR NEW.payload->>'document_sha256' IS DISTINCT FROM NEW.document_sha256 THEN
              RAISE EXCEPTION 'Amendment payload binding invalid' USING ERRCODE='23514'; END IF;
            RETURN NEW;
          END; $$ LANGUAGE plpgsql""")
        op.execute('CREATE TRIGGER review_submission_amendment_guard BEFORE INSERT OR UPDATE OR DELETE ON review_submission_amendments FOR EACH ROW EXECUTE FUNCTION review_submission_amendment_guard()')
        op.execute("""CREATE OR REPLACE FUNCTION review_adjudication_amendment_guard() RETURNS trigger AS $$ BEGIN
          IF EXISTS(SELECT 1 FROM review_assignments a JOIN review_submission_amendments m ON m.assignment_id=a.id
            WHERE a.study_id=NEW.study_id) THEN
            RAISE EXCEPTION 'Adjudication cannot omit an existing review amendment' USING ERRCODE='23514'; END IF;
          RETURN NEW; END; $$ LANGUAGE plpgsql""")
        op.execute('CREATE TRIGGER review_adjudication_amendment_guard BEFORE INSERT ON adjudication_assignments FOR EACH ROW EXECUTE FUNCTION review_adjudication_amendment_guard()')
    else:
        op.execute("""CREATE TRIGGER review_submission_amendment_insert_guard BEFORE INSERT ON review_submission_amendments BEGIN
          SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM independent_review_submissions s WHERE s.id=NEW.submission_id
            AND s.assignment_id=NEW.assignment_id AND s.owner_id=NEW.owner_id AND s.record_sha256=NEW.parent_submission_sha256)
            THEN RAISE(ABORT,'Amendment parent binding invalid') END;
          SELECT CASE WHEN EXISTS(SELECT 1 FROM review_assignments a JOIN adjudication_assignments j ON j.study_id=a.study_id
            WHERE a.id=NEW.assignment_id) THEN RAISE(ABORT,'Amendments close when adjudication is assigned') END;
          SELECT CASE WHEN NEW.revision=1 AND (NEW.previous_id IS NOT NULL OR NEW.previous_sha256 IS NOT NULL)
            THEN RAISE(ABORT,'Invalid initial amendment revision') END;
          SELECT CASE WHEN NEW.revision>1 AND NOT EXISTS(SELECT 1 FROM review_submission_amendments p
            WHERE p.id=NEW.previous_id AND p.assignment_id=NEW.assignment_id AND p.revision=NEW.revision-1
            AND p.record_sha256=NEW.previous_sha256 AND NOT EXISTS(SELECT 1 FROM review_submission_amendments n
              WHERE n.assignment_id=NEW.assignment_id AND n.revision>p.revision))
            THEN RAISE(ABORT,'Amendment revision is stale') END;
          SELECT CASE WHEN NEW.payload IS NULL OR NEW.clinical_gate_authorized<>0 OR NEW.training_release_authorized<>0
            THEN RAISE(ABORT,'Amendment authorization invalid') END;
        END""")
        for action in ('UPDATE', 'DELETE'):
            op.execute(f"CREATE TRIGGER review_submission_amendment_{action.lower()}_guard BEFORE {action} ON review_submission_amendments BEGIN SELECT RAISE(ABORT,'Review amendments are immutable'); END")
        op.execute("""CREATE TRIGGER review_adjudication_amendment_guard BEFORE INSERT ON adjudication_assignments BEGIN
          SELECT CASE WHEN EXISTS(SELECT 1 FROM review_assignments a JOIN review_submission_amendments m ON m.assignment_id=a.id
            WHERE a.study_id=NEW.study_id) THEN RAISE(ABORT,'Adjudication cannot omit an existing review amendment') END;
        END""")


def downgrade():
    if op.get_bind().dialect.name == 'postgresql':
        op.execute('DROP TRIGGER review_adjudication_amendment_guard ON adjudication_assignments')
        op.execute('DROP FUNCTION review_adjudication_amendment_guard()')
        op.execute('DROP TRIGGER review_submission_amendment_guard ON review_submission_amendments')
        op.execute('DROP FUNCTION review_submission_amendment_guard()')
    else:
        op.execute('DROP TRIGGER review_adjudication_amendment_guard')
        op.execute('DROP TRIGGER review_submission_amendment_insert_guard')
        op.execute('DROP TRIGGER review_submission_amendment_update_guard')
        op.execute('DROP TRIGGER review_submission_amendment_delete_guard')
    op.drop_index('ix_review_submission_amendments_assignment_id', table_name='review_submission_amendments')
    op.drop_table('review_submission_amendments')
