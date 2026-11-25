"""Append-only third-reader adjudication. No credential records are seeded.

Downgrade destroys new review/credential records and is not an application
rollback strategy. No existing application data is transformed.
"""
from alembic import op
import sqlalchemy as sa
revision = '0015_review_adjudication'
down_revision = '0014_review_submissions'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('reviewer_credentials',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('reviewer_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('verified_by', sa.Integer(), sa.ForeignKey('users.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('evidence_reference', sa.String(500), nullable=False), sa.Column('evidence_sha256', sa.String(64), nullable=False),
        sa.Column('scope', sa.String(128), nullable=False), sa.Column('verified_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('valid_until', sa.DateTime(timezone=True), nullable=False),
        sa.Column('revoked', sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.CheckConstraint('valid_until > verified_at', name='ck_reader_credential_dates'))
    op.create_index('ix_reviewer_credentials_reviewer_id', 'reviewer_credentials', ['reviewer_id'])
    op.create_table('adjudication_assignments',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('study_id', sa.String(36), sa.ForeignKey('review_studies.id', ondelete='RESTRICT'), nullable=False, unique=True),
        sa.Column('reviewer_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('coordinator_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('credential_id', sa.String(36), sa.ForeignKey('reviewer_credentials.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('r1_submission_id', sa.String(36), sa.ForeignKey('independent_review_submissions.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('r2_submission_id', sa.String(36), sa.ForeignKey('independent_review_submissions.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('r1_sha256', sa.String(64), nullable=False), sa.Column('r2_sha256', sa.String(64), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_index('ix_adjudication_assignments_reviewer_id', 'adjudication_assignments', ['reviewer_id'])
    op.create_table('adjudication_versions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('assignment_id', sa.String(36), sa.ForeignKey('adjudication_assignments.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('owner_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('previous_id', sa.String(36), sa.ForeignKey('adjudication_versions.id', ondelete='RESTRICT')),
        sa.Column('previous_sha256', sa.String(64)), sa.Column('document_sha256', sa.String(64), nullable=False),
        sa.Column('record_sha256', sa.String(64), nullable=False), sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('final', sa.Boolean(), nullable=False),
        sa.Column('clinical_gate_authorized', sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column('training_release_authorized', sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('assignment_id', 'revision', name='uq_adjudication_revision'),
        sa.CheckConstraint('revision > 0', name='ck_adjudication_revision'),
        sa.CheckConstraint('NOT clinical_gate_authorized AND NOT training_release_authorized', name='ck_adjudication_no_release'))
    op.create_index('ix_adjudication_versions_assignment_id', 'adjudication_versions', ['assignment_id'])
    if op.get_bind().dialect.name == 'postgresql':
        op.execute("""CREATE OR REPLACE FUNCTION adjudication_assignment_guard() RETURNS trigger AS $$ BEGIN
          IF TG_OP<>'INSERT' THEN RAISE EXCEPTION 'Adjudication bindings immutable' USING ERRCODE='23514'; END IF;
          PERFORM id FROM users WHERE id=NEW.reviewer_id AND is_active AND role='Clinician' FOR SHARE;
          IF NOT FOUND OR NEW.reviewer_id=NEW.coordinator_id
            OR EXISTS(SELECT 1 FROM review_assignments WHERE reviewer_id=NEW.reviewer_id)
            OR NOT EXISTS(SELECT 1 FROM users WHERE id=NEW.coordinator_id AND role='Admin' AND is_active)
            OR NOT EXISTS(SELECT 1 FROM reviewer_credentials c WHERE c.id=NEW.credential_id AND c.reviewer_id=NEW.reviewer_id
              AND NOT c.revoked AND c.verified_at<=CURRENT_TIMESTAMP AND c.valid_until>CURRENT_TIMESTAMP
              AND c.scope='coronary-cta-lesion-adjudication' AND length(trim(c.evidence_reference))>0
              AND c.evidence_sha256 ~ '^[a-f0-9]{64}$') THEN
            RAISE EXCEPTION 'Qualified separate adjudicator required' USING ERRCODE='23514'; END IF;
          IF NOT EXISTS(SELECT 1 FROM independent_review_submissions x JOIN review_assignments a ON a.id=x.assignment_id
            WHERE x.id=NEW.r1_submission_id AND a.study_id=NEW.study_id AND a.slot='R1' AND x.record_sha256=NEW.r1_sha256)
            OR NOT EXISTS(SELECT 1 FROM independent_review_submissions x JOIN review_assignments a ON a.id=x.assignment_id
            WHERE x.id=NEW.r2_submission_id AND a.study_id=NEW.study_id AND a.slot='R2' AND x.record_sha256=NEW.r2_sha256) THEN
            RAISE EXCEPTION 'Both frozen independent reviews required' USING ERRCODE='23514'; END IF;
          RETURN NEW; END; $$ LANGUAGE plpgsql""")
        op.execute('CREATE TRIGGER adjudication_assignment_guard BEFORE INSERT OR UPDATE OR DELETE ON adjudication_assignments FOR EACH ROW EXECUTE FUNCTION adjudication_assignment_guard()')
        op.execute("""CREATE OR REPLACE FUNCTION adjudication_version_guard() RETURNS trigger AS $$ DECLARE a adjudication_assignments%ROWTYPE; p adjudication_versions%ROWTYPE; BEGIN
          IF TG_OP<>'INSERT' THEN RAISE EXCEPTION 'Adjudication history immutable' USING ERRCODE='23514'; END IF;
          SELECT * INTO a FROM adjudication_assignments WHERE id=NEW.assignment_id FOR UPDATE;
          IF NOT FOUND OR a.reviewer_id<>NEW.owner_id OR NOT EXISTS(SELECT 1 FROM users WHERE id=NEW.owner_id AND is_active AND role='Clinician')
            OR NOT EXISTS(SELECT 1 FROM reviewer_credentials WHERE id=a.credential_id AND NOT revoked
              AND verified_at<=CURRENT_TIMESTAMP AND valid_until>CURRENT_TIMESTAMP) THEN
            RAISE EXCEPTION 'Adjudicator authority unavailable' USING ERRCODE='23514'; END IF;
          SELECT * INTO p FROM adjudication_versions WHERE assignment_id=a.id ORDER BY revision DESC LIMIT 1;
          IF FOUND THEN
            IF p.final OR NEW.revision<>p.revision+1 OR NEW.previous_id IS DISTINCT FROM p.id OR NEW.previous_sha256 IS DISTINCT FROM p.record_sha256 THEN
              RAISE EXCEPTION 'Adjudication revision frozen or stale' USING ERRCODE='23514'; END IF;
          ELSIF NEW.revision<>1 OR NEW.previous_id IS NOT NULL OR NEW.previous_sha256 IS NOT NULL THEN
            RAISE EXCEPTION 'Invalid first adjudication version' USING ERRCODE='23514'; END IF;
          IF NEW.payload::jsonb->'clinical_gate_authorized' IS DISTINCT FROM 'false'::jsonb
            OR NEW.payload::jsonb->'training_release_authorized' IS DISTINCT FROM 'false'::jsonb
            OR NEW.payload->>'assignment_id' IS DISTINCT FROM a.id
            OR NEW.payload::jsonb->'document'->>'assignment_id' IS DISTINCT FROM a.id
            OR NEW.payload::jsonb->'document'->>'r1_submission_sha256' IS DISTINCT FROM a.r1_sha256
            OR NEW.payload::jsonb->'document'->>'r2_submission_sha256' IS DISTINCT FROM a.r2_sha256
            OR NEW.payload::jsonb->'document'->'clinical_gate_authorized' IS DISTINCT FROM 'false'::jsonb
            OR NEW.payload::jsonb->'document'->'training_release_authorized' IS DISTINCT FROM 'false'::jsonb THEN
            RAISE EXCEPTION 'Adjudication provenance invalid' USING ERRCODE='23514'; END IF;
          RETURN NEW; END; $$ LANGUAGE plpgsql""")
        op.execute('CREATE TRIGGER adjudication_version_guard BEFORE INSERT OR UPDATE OR DELETE ON adjudication_versions FOR EACH ROW EXECUTE FUNCTION adjudication_version_guard()')
        op.execute("""CREATE OR REPLACE FUNCTION adjudicator_reader_separation() RETURNS trigger AS $$ BEGIN
          IF EXISTS(SELECT 1 FROM adjudication_assignments WHERE reviewer_id=NEW.reviewer_id) THEN
            RAISE EXCEPTION 'Adjudicator cannot become an independent reader' USING ERRCODE='23514'; END IF;
          RETURN NEW; END; $$ LANGUAGE plpgsql""")
        op.execute('CREATE TRIGGER adjudicator_reader_separation BEFORE INSERT OR UPDATE ON review_assignments FOR EACH ROW EXECUTE FUNCTION adjudicator_reader_separation()')
    else:
        for table in ['adjudication_assignments', 'adjudication_versions']:
            for action in ['UPDATE', 'DELETE']:
                op.execute(f"CREATE TRIGGER {table}_{action.lower()} BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT,'Adjudication immutable'); END")


def downgrade():
    if op.get_bind().dialect.name == 'postgresql':
        op.execute('DROP TRIGGER adjudicator_reader_separation ON review_assignments')
        op.execute('DROP FUNCTION adjudicator_reader_separation()')
    for table in ['adjudication_versions', 'adjudication_assignments', 'reviewer_credentials']:
        op.drop_table(table)
    if op.get_bind().dialect.name == 'postgresql':
        op.execute('DROP FUNCTION adjudication_version_guard()')
        op.execute('DROP FUNCTION adjudication_assignment_guard()')
