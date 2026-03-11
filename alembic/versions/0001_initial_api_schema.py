"""Initial API schema

Revision ID: 0001_initial_api_schema
Revises: None
Create Date: 2026-03-10 23:59:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0001_initial_api_schema"
down_revision = None
branch_labels = None
depends_on = None


run_status_enum = sa.Enum("QUEUED", "RUNNING", "SUCCEEDED", "FAILED", name="runstatus")
experiment_kind_enum = sa.Enum("OPTIMIZER", "WALKFORWARD", name="experimentkind")


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "backtest_runs" not in existing_tables:
        op.create_table(
            "backtest_runs",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("symbol", sa.String(length=32), nullable=False),
            sa.Column("strategy_name", sa.String(length=64), nullable=False),
            sa.Column("provider_name", sa.String(length=64), nullable=False),
            sa.Column("status", run_status_enum, nullable=False),
            sa.Column("request_payload", sa.JSON(), nullable=False),
            sa.Column("response_payload", sa.JSON(), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("idx_backtest_runs_created_at", "backtest_runs", ["created_at"], unique=False)
        op.create_index(op.f("ix_backtest_runs_status"), "backtest_runs", ["status"], unique=False)
        op.create_index(op.f("ix_backtest_runs_strategy_name"), "backtest_runs", ["strategy_name"], unique=False)
        op.create_index(op.f("ix_backtest_runs_symbol"), "backtest_runs", ["symbol"], unique=False)

    if "experiment_runs" not in existing_tables:
        op.create_table(
            "experiment_runs",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("kind", experiment_kind_enum, nullable=False),
            sa.Column("symbol", sa.String(length=32), nullable=False),
            sa.Column("strategy_name", sa.String(length=64), nullable=False),
            sa.Column("provider_name", sa.String(length=64), nullable=False),
            sa.Column("status", run_status_enum, nullable=False),
            sa.Column("request_payload", sa.JSON(), nullable=False),
            sa.Column("response_payload", sa.JSON(), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("idx_experiment_runs_created_at", "experiment_runs", ["created_at"], unique=False)
        op.create_index(op.f("ix_experiment_runs_kind"), "experiment_runs", ["kind"], unique=False)
        op.create_index(op.f("ix_experiment_runs_status"), "experiment_runs", ["status"], unique=False)
        op.create_index(op.f("ix_experiment_runs_strategy_name"), "experiment_runs", ["strategy_name"], unique=False)
        op.create_index(op.f("ix_experiment_runs_symbol"), "experiment_runs", ["symbol"], unique=False)

    if "strategy_snapshots" not in existing_tables:
        op.create_table(
            "strategy_snapshots",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("strategy_name", sa.String(length=64), nullable=False),
            sa.Column("description", sa.String(length=256), nullable=False),
            sa.Column("default_params", sa.JSON(), nullable=False),
            sa.Column("enabled", sa.Boolean(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("strategy_name", name="uq_strategy_snapshots_name"),
        )

    if "run_metric_snapshots" not in existing_tables:
        op.create_table(
            "run_metric_snapshots",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("run_type", sa.String(length=32), nullable=False),
            sa.Column("run_id", sa.String(length=36), nullable=False),
            sa.Column("cagr", sa.Float(), nullable=True),
            sa.Column("max_drawdown", sa.Float(), nullable=True),
            sa.Column("sharpe", sa.Float(), nullable=True),
            sa.Column("annual_turnover", sa.Float(), nullable=True),
            sa.Column("data_years", sa.Float(), nullable=True),
            sa.Column("metadata_payload", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("backtest_run_id", sa.String(length=36), nullable=True),
            sa.Column("experiment_run_id", sa.String(length=36), nullable=True),
            sa.ForeignKeyConstraint(["backtest_run_id"], ["backtest_runs.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["experiment_run_id"], ["experiment_runs.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_run_metric_snapshots_run_id"), "run_metric_snapshots", ["run_id"], unique=False)
        op.create_index(op.f("ix_run_metric_snapshots_run_type"), "run_metric_snapshots", ["run_type"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_run_metric_snapshots_run_type"), table_name="run_metric_snapshots")
    op.drop_index(op.f("ix_run_metric_snapshots_run_id"), table_name="run_metric_snapshots")
    op.drop_table("run_metric_snapshots")

    op.drop_table("strategy_snapshots")

    op.drop_index(op.f("ix_experiment_runs_symbol"), table_name="experiment_runs")
    op.drop_index(op.f("ix_experiment_runs_strategy_name"), table_name="experiment_runs")
    op.drop_index(op.f("ix_experiment_runs_status"), table_name="experiment_runs")
    op.drop_index(op.f("ix_experiment_runs_kind"), table_name="experiment_runs")
    op.drop_index("idx_experiment_runs_created_at", table_name="experiment_runs")
    op.drop_table("experiment_runs")

    op.drop_index(op.f("ix_backtest_runs_symbol"), table_name="backtest_runs")
    op.drop_index(op.f("ix_backtest_runs_strategy_name"), table_name="backtest_runs")
    op.drop_index(op.f("ix_backtest_runs_status"), table_name="backtest_runs")
    op.drop_index("idx_backtest_runs_created_at", table_name="backtest_runs")
    op.drop_table("backtest_runs")

    experiment_kind_enum.drop(op.get_bind(), checkfirst=True)
    run_status_enum.drop(op.get_bind(), checkfirst=True)
