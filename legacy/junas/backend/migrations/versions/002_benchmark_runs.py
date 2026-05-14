"""add benchmark run and score tables

Revision ID: 002_benchmark_runs
Revises: 001_initial
Create Date: 2026-04-01 15:10:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "002_benchmark_runs"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "benchmark_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("run_name", sa.String(length=100), nullable=False),
        sa.Column("model_name", sa.String(length=200), nullable=False),
        sa.Column("model_path", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("requested_tasks", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("results", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("is_published_baseline", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("tasks_completed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tasks_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("avg_micro_f1", sa.Float(), nullable=True),
        sa.Column("avg_macro_f1", sa.Float(), nullable=True),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index("ix_benchmark_runs_status", "benchmark_runs", ["status"])
    op.create_index("ix_benchmark_runs_created_at", "benchmark_runs", ["created_at"])

    op.create_table(
        "benchmark_scores",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_name", sa.String(length=50), nullable=False),
        sa.Column("task_config", sa.String(length=50), nullable=False),
        sa.Column("micro_f1", sa.Float(), nullable=True),
        sa.Column("macro_f1", sa.Float(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["benchmark_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "task_config", name="uq_benchmark_scores_run_task"),
    )

    op.create_index("ix_benchmark_scores_run_id", "benchmark_scores", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_benchmark_scores_run_id", table_name="benchmark_scores")
    op.drop_table("benchmark_scores")

    op.drop_index("ix_benchmark_runs_created_at", table_name="benchmark_runs")
    op.drop_index("ix_benchmark_runs_status", table_name="benchmark_runs")
    op.drop_table("benchmark_runs")
