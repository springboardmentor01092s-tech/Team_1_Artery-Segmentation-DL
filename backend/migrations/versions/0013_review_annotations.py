"""Source-bound manual worksheets and append-only revision evidence.

Downgrade deletes all new worksheets/history. No old table or data transformed.
"""
from alembic import op
import sqlalchemy as sa
revision='0013_review_annotations'
down_revision='0012_ct_review_assignments'
branch_labels=None
depends_on=None

def upgrade():
    for name,versioned in [('review_annotation_drafts',False),('review_annotation_versions',True)]:
        columns=[sa.Column('assignment_id',sa.String(36),primary_key=not versioned,nullable=False),
            sa.Column('owner_id',sa.Integer(),sa.ForeignKey('users.id',ondelete='RESTRICT'),nullable=False),
            sa.Column('document',sa.JSON(),nullable=False),sa.Column('revision',sa.Integer(),nullable=False),
            sa.Column('clinical_gate_authorized',sa.Boolean(),server_default=sa.false(),nullable=False),
            sa.Column('training_release_authorized',sa.Boolean(),server_default=sa.false(),nullable=False),
            sa.Column('created_at' if versioned else 'updated_at',sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),
            sa.ForeignKeyConstraint(['assignment_id','owner_id'],['review_assignments.id','review_assignments.reviewer_id'],ondelete='RESTRICT'),
            sa.CheckConstraint('revision>0',name='ck_review_annotation_version_revision' if versioned else 'ck_review_annotation_revision'),
            sa.CheckConstraint('NOT clinical_gate_authorized AND NOT training_release_authorized',name='ck_review_annotation_version_no_release' if versioned else 'ck_review_annotation_no_release')]
        if versioned:columns += [sa.Column('id',sa.String(36),primary_key=True),sa.Column('content_sha256',sa.String(64),nullable=False),sa.UniqueConstraint('assignment_id','revision',name='uq_review_annotation_version')]
        op.create_table(name,*columns)
    op.create_index('ix_review_annotation_versions_assignment_id','review_annotation_versions',['assignment_id'])
    if op.get_bind().dialect.name=='postgresql':
        op.execute("""CREATE OR REPLACE FUNCTION review_annotation_guard() RETURNS trigger AS $$ BEGIN
          IF TG_OP='DELETE' OR TG_TABLE_NAME='review_annotation_versions' AND TG_OP<>'INSERT' THEN
            RAISE EXCEPTION 'Review annotation history cannot be overwritten or deleted' USING ERRCODE='23514'; END IF;
          PERFORM id FROM users WHERE id=NEW.owner_id AND is_active AND role IN ('Clinician','Admin') FOR SHARE;
          IF NOT FOUND THEN RAISE EXCEPTION 'Annotation author unavailable' USING ERRCODE='23514'; END IF;
          IF NEW.document::jsonb->'clinical_gate_authorized' IS DISTINCT FROM 'false'::jsonb
             OR NEW.document::jsonb->'training_release_authorized' IS DISTINCT FROM 'false'::jsonb
             OR NEW.document::jsonb->'reader_qualification_verified' IS DISTINCT FROM 'false'::jsonb
             OR NEW.document::jsonb->'reader_independence_verified' IS DISTINCT FROM 'false'::jsonb
             OR NOT EXISTS(SELECT 1 FROM review_assignments a JOIN review_studies s ON s.id=a.study_id
                WHERE a.id=NEW.assignment_id AND a.reviewer_id=NEW.owner_id
                  AND NEW.document->>'assignment_id'=a.id
                  AND NEW.document->>'protocol_version'=s.protocol_version
                  AND NEW.document::jsonb->'source'=s.source_json::jsonb
                  AND NEW.document->>'schema_version'='independent-lesion-review/0.1') THEN
             RAISE EXCEPTION 'Annotation source or authorization binding invalid' USING ERRCODE='23514'; END IF;
          IF TG_TABLE_NAME='review_annotation_drafts' AND (TG_OP='INSERT' AND NEW.revision<>1 OR TG_OP='UPDATE' AND
            (NEW.assignment_id<>OLD.assignment_id OR NEW.owner_id<>OLD.owner_id OR NEW.revision<>OLD.revision+1)) THEN
            RAISE EXCEPTION 'Annotation revision conflict' USING ERRCODE='23514'; END IF;
          RETURN NEW; END; $$ LANGUAGE plpgsql""")
        for table in ['review_annotation_drafts','review_annotation_versions']:
            op.execute(f'CREATE TRIGGER {table}_guard BEFORE INSERT OR UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION review_annotation_guard()')
    else:
        for table in ['review_annotation_drafts','review_annotation_versions']:
            op.execute(f"CREATE TRIGGER {table}_delete BEFORE DELETE ON {table} BEGIN SELECT RAISE(ABORT,'Review annotation deletion unavailable'); END")
        op.execute("CREATE TRIGGER review_annotation_version_update BEFORE UPDATE ON review_annotation_versions BEGIN SELECT RAISE(ABORT,'Review history immutable'); END")
        for action in ['INSERT','UPDATE']:
            revision='NEW.revision<>1' if action=='INSERT' else 'NEW.assignment_id<>OLD.assignment_id OR NEW.owner_id<>OLD.owner_id OR NEW.revision<>OLD.revision+1'
            op.execute(f"""CREATE TRIGGER review_annotation_draft_{action.lower()} BEFORE {action} ON review_annotation_drafts BEGIN
              SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM users WHERE id=NEW.owner_id AND is_active=1 AND role IN ('Clinician','Admin'))
              OR ({revision}) THEN RAISE(ABORT,'Annotation author or revision invalid') END; END""")

def downgrade():
    op.drop_table('review_annotation_versions');op.drop_table('review_annotation_drafts')
    if op.get_bind().dialect.name=='postgresql':op.execute('DROP FUNCTION review_annotation_guard()')
