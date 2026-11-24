"""Research-only review history; no existing case/result rows are transformed.

Downgrade deletes review history. It does not delete cases, outputs or uploads.
Stored case status is a workflow hint; /cases/{id}/workflow verifies current evidence.
"""
from alembic import op
import sqlalchemy as sa

revision = "0010_case_reviews"
down_revision = "0009_evaluations"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("segmentation_results") as batch:
        batch.create_unique_constraint("uq_segmentation_result_case", ["id", "case_id"])
    op.create_table(
        "case_reviews",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("case_id", sa.Integer(), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("segmentation_result_id", sa.String(36), nullable=False),
        sa.Column("reviewer_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("reviewer_role", sa.String(50), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("outcome", sa.String(40), nullable=False),
        sa.Column("note", sa.Text()),
        sa.Column("source_sha256", sa.String(64), nullable=False),
        sa.Column("checkpoint_sha256", sa.String(64), nullable=False),
        sa.Column("mask_sha256", sa.String(64), nullable=False),
        sa.Column("probabilities_sha256", sa.String(64), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["segmentation_result_id", "case_id"],
                                ["segmentation_results.id", "segmentation_results.case_id"], ondelete="CASCADE"),
        sa.UniqueConstraint("segmentation_result_id", name="uq_case_review_run"),
        sa.CheckConstraint("outcome IN ('accepted_for_research', 'changes_requested')", name="ck_case_review_outcome"),
    )
    op.create_index("ix_case_reviews_case_id", "case_reviews", ["case_id"])


def downgrade():
    op.drop_table("case_reviews")
    with op.batch_alter_table("segmentation_results") as batch:
        batch.drop_constraint("uq_segmentation_result_case", type_="unique")
