"""Freeze independent unverified reviews, preserving original draft versions.

Downgrade is deliberately destructive to new submissions and requires separate
operational approval; no downgrade is part of deployment rollback.
"""
from alembic import op
import sqlalchemy as sa
revision='0014_review_submissions'
down_revision='0013_review_annotations'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('independent_review_submissions',
        sa.Column('id',sa.String(36),primary_key=True),sa.Column('assignment_id',sa.String(36),nullable=False),
        sa.Column('owner_id',sa.Integer(),sa.ForeignKey('users.id',ondelete='RESTRICT'),nullable=False),
        sa.Column('version_id',sa.String(36),sa.ForeignKey('review_annotation_versions.id',ondelete='RESTRICT'),nullable=False),
        sa.Column('document_sha256',sa.String(64),nullable=False),sa.Column('record_sha256',sa.String(64),nullable=False),
        sa.Column('payload',sa.JSON(),nullable=False),sa.Column('clinical_gate_authorized',sa.Boolean(),server_default=sa.false(),nullable=False),
        sa.Column('training_release_authorized',sa.Boolean(),server_default=sa.false(),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),
        sa.ForeignKeyConstraint(['assignment_id','owner_id'],['review_assignments.id','review_assignments.reviewer_id'],ondelete='RESTRICT'),
        sa.UniqueConstraint('assignment_id',name='uq_independent_review_assignment'),
        sa.CheckConstraint('NOT clinical_gate_authorized AND NOT training_release_authorized',name='ck_independent_review_no_release'))
    if op.get_bind().dialect.name=='postgresql':
        op.execute("""CREATE OR REPLACE FUNCTION independent_review_guard() RETURNS trigger AS $$ BEGIN
          IF TG_OP<>'INSERT' THEN RAISE EXCEPTION 'Independent submissions are immutable' USING ERRCODE='23514'; END IF;
          PERFORM id FROM users WHERE id=NEW.owner_id AND is_active AND role IN ('Clinician','Admin') FOR SHARE;
          IF NOT FOUND OR NOT EXISTS(SELECT 1 FROM review_annotation_versions v
            JOIN review_assignments a ON a.id=v.assignment_id JOIN review_studies s ON s.id=a.study_id WHERE v.id=NEW.version_id
            AND v.assignment_id=NEW.assignment_id AND v.owner_id=NEW.owner_id AND v.content_sha256=NEW.document_sha256
            AND NEW.payload::jsonb->'document'=v.document::jsonb AND NEW.payload::jsonb->'source'=s.source_json::jsonb
            AND NEW.payload->>'protocol_version'=s.protocol_version
            AND NEW.payload::jsonb->'reviewer_id'=to_jsonb(NEW.owner_id))
            OR NEW.payload::jsonb->'clinical_gate_authorized' IS DISTINCT FROM 'false'::jsonb
            OR NEW.payload::jsonb->'training_release_authorized' IS DISTINCT FROM 'false'::jsonb
            OR NEW.payload->>'id' IS DISTINCT FROM NEW.id
            OR NEW.payload->>'assignment_id' IS DISTINCT FROM NEW.assignment_id THEN
            RAISE EXCEPTION 'Independent submission binding invalid' USING ERRCODE='23514'; END IF;
          RETURN NEW; END; $$ LANGUAGE plpgsql""")
        op.execute('CREATE TRIGGER independent_review_guard BEFORE INSERT OR UPDATE OR DELETE ON independent_review_submissions FOR EACH ROW EXECUTE FUNCTION independent_review_guard()')
        op.execute("""CREATE OR REPLACE FUNCTION submitted_annotation_freeze() RETURNS trigger AS $$ DECLARE key text; BEGIN
          IF TG_OP='DELETE' THEN key=OLD.assignment_id; ELSE key=NEW.assignment_id; END IF;
          IF EXISTS(SELECT 1 FROM independent_review_submissions WHERE assignment_id=key) THEN
            RAISE EXCEPTION 'Submitted annotation cannot be edited or replaced' USING ERRCODE='23514'; END IF;
          IF TG_OP='DELETE' THEN RETURN OLD; END IF; RETURN NEW; END; $$ LANGUAGE plpgsql""")
        for table in ['review_annotation_drafts','review_annotation_versions']:
            op.execute(f'CREATE TRIGGER {table}_submission_freeze BEFORE INSERT OR UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION submitted_annotation_freeze()')
    else:
        for action in ['UPDATE','DELETE']:
            op.execute(f"CREATE TRIGGER independent_review_{action.lower()} BEFORE {action} ON independent_review_submissions BEGIN SELECT RAISE(ABORT,'Independent submission immutable'); END")
        for table in ['review_annotation_drafts','review_annotation_versions']:
            for action in ['INSERT','UPDATE','DELETE']:
                key='OLD' if action=='DELETE' else 'NEW'
                op.execute(f"""CREATE TRIGGER {table}_freeze_{action.lower()} BEFORE {action} ON {table} BEGIN
                  SELECT CASE WHEN EXISTS(SELECT 1 FROM independent_review_submissions WHERE assignment_id={key}.assignment_id)
                  THEN RAISE(ABORT,'Submitted annotation immutable') END; END""")

def downgrade():
    if op.get_bind().dialect.name=='postgresql':
        for table in ['review_annotation_drafts','review_annotation_versions']:op.execute(f'DROP TRIGGER {table}_submission_freeze ON {table}')
        op.execute('DROP FUNCTION submitted_annotation_freeze()')
    else:
        for table in ['review_annotation_drafts','review_annotation_versions']:
            for action in ['insert','update','delete']:op.execute(f'DROP TRIGGER {table}_freeze_{action}')
    op.drop_table('independent_review_submissions')
    if op.get_bind().dialect.name=='postgresql':op.execute('DROP FUNCTION independent_review_guard()')
