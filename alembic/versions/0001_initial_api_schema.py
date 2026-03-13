"""Initial GobyShrimp API schema

Revision ID: 0001_initial_api_schema
Revises: None
Create Date: 2026-03-10 23:59:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0001_initial_api_schema"
down_revision = None
branch_labels = None
depends_on = None


run_status_enum = sa.Enum("queued", "running", "succeeded", "failed", name="runstatus")
experiment_kind_enum = sa.Enum("optimizer", "walkforward", name="experimentkind")
proposal_status_enum = sa.Enum("candidate", "active", "rejected", "archived", name="proposalstatus")
risk_action_enum = sa.Enum(
    "reject",
    "keep_candidate",
    "promote_to_paper",
    "pause_active",
    "rollback_to_previous_stable",
    name="riskdecisionaction",
)
event_type_enum = sa.Enum("macro", name="eventtype")


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "strategy_proposals" not in existing_tables:
        op.create_table(
            "strategy_proposals",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("run_id", sa.String(length=64), nullable=False),
            sa.Column("title", sa.String(length=128), nullable=False),
            sa.Column("symbol", sa.String(length=32), nullable=False),
            sa.Column("market_scope", sa.String(length=16), nullable=False),
            sa.Column("thesis", sa.Text(), nullable=False),
            sa.Column("source_kind", sa.String(length=32), nullable=False),
            sa.Column("provider_status", sa.String(length=32), nullable=False, server_default="mock"),
            sa.Column("provider_model", sa.String(length=64), nullable=False, server_default=""),
            sa.Column("provider_message", sa.Text(), nullable=False, server_default=""),
            sa.Column("market_snapshot_hash", sa.String(length=64), nullable=False),
            sa.Column("event_digest_hash", sa.String(length=64), nullable=False),
            sa.Column("strategy_dsl", sa.JSON(), nullable=False),
            sa.Column("debate_report", sa.JSON(), nullable=False),
            sa.Column("evidence_pack", sa.JSON(), nullable=False),
            sa.Column("features_used", sa.JSON(), nullable=False),
            sa.Column("deterministic_score", sa.Float(), nullable=False),
            sa.Column("llm_score", sa.Float(), nullable=False),
            sa.Column("final_score", sa.Float(), nullable=False),
            sa.Column("status", proposal_status_enum, nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("run_id"),
        )
        op.create_index(op.f("ix_strategy_proposals_run_id"), "strategy_proposals", ["run_id"], unique=True)
        op.create_index(op.f("ix_strategy_proposals_symbol"), "strategy_proposals", ["symbol"], unique=False)
        op.create_index(op.f("ix_strategy_proposals_status"), "strategy_proposals", ["status"], unique=False)

    if "backtest_runs" not in existing_tables:
        op.create_table(
            "backtest_runs",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("symbol", sa.String(length=32), nullable=False),
            sa.Column("strategy_name", sa.String(length=64), nullable=False),
            sa.Column("provider_name", sa.String(length=64), nullable=False),
            sa.Column("proposal_id", sa.String(length=36), nullable=True),
            sa.Column("status", run_status_enum, nullable=False),
            sa.Column("request_payload", sa.JSON(), nullable=False),
            sa.Column("response_payload", sa.JSON(), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["proposal_id"], ["strategy_proposals.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("idx_backtest_runs_created_at", "backtest_runs", ["created_at"], unique=False)
        op.create_index(op.f("ix_backtest_runs_proposal_id"), "backtest_runs", ["proposal_id"], unique=False)
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
            sa.Column("proposal_id", sa.String(length=36), nullable=True),
            sa.Column("status", run_status_enum, nullable=False),
            sa.Column("request_payload", sa.JSON(), nullable=False),
            sa.Column("response_payload", sa.JSON(), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["proposal_id"], ["strategy_proposals.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("idx_experiment_runs_created_at", "experiment_runs", ["created_at"], unique=False)
        op.create_index(op.f("ix_experiment_runs_kind"), "experiment_runs", ["kind"], unique=False)
        op.create_index(op.f("ix_experiment_runs_proposal_id"), "experiment_runs", ["proposal_id"], unique=False)
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

    if "event_records" not in existing_tables:
        op.create_table(
            "event_records",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("event_id", sa.String(length=96), nullable=False),
            sa.Column("event_type", event_type_enum, nullable=False),
            sa.Column("market_scope", sa.String(length=16), nullable=False),
            sa.Column("symbol_scope", sa.String(length=32), nullable=False),
            sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("source", sa.String(length=64), nullable=False),
            sa.Column("title", sa.String(length=256), nullable=False),
            sa.Column("body_ref", sa.Text(), nullable=True),
            sa.Column("tags", sa.JSON(), nullable=False),
            sa.Column("importance", sa.Float(), nullable=False),
            sa.Column("sentiment_hint", sa.Float(), nullable=False),
            sa.Column("metadata_payload", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("event_id"),
        )
        op.create_index(op.f("ix_event_records_event_id"), "event_records", ["event_id"], unique=True)
        op.create_index(op.f("ix_event_records_event_type"), "event_records", ["event_type"], unique=False)
        op.create_index(op.f("ix_event_records_published_at"), "event_records", ["published_at"], unique=False)

    if "daily_event_digests" not in existing_tables:
        op.create_table(
            "daily_event_digests",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("trade_date", sa.String(length=10), nullable=False),
            sa.Column("market_scope", sa.String(length=16), nullable=False),
            sa.Column("symbol_scope", sa.String(length=32), nullable=False),
            sa.Column("macro_summary", sa.Text(), nullable=False),
            sa.Column("event_scores", sa.JSON(), nullable=False),
            sa.Column("digest_hash", sa.String(length=64), nullable=False),
            sa.Column("event_ids", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("trade_date", "market_scope", "symbol_scope", name="uq_daily_digest_scope"),
        )
        op.create_index(op.f("ix_daily_event_digests_digest_hash"), "daily_event_digests", ["digest_hash"], unique=False)
        op.create_index(op.f("ix_daily_event_digests_trade_date"), "daily_event_digests", ["trade_date"], unique=False)

    if "risk_decisions" not in existing_tables:
        op.create_table(
            "risk_decisions",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("decision_id", sa.String(length=64), nullable=False),
            sa.Column("run_id", sa.String(length=64), nullable=False),
            sa.Column("proposal_id", sa.String(length=36), nullable=False),
            sa.Column("action", risk_action_enum, nullable=False),
            sa.Column("deterministic_score", sa.Float(), nullable=False),
            sa.Column("llm_score", sa.Float(), nullable=False),
            sa.Column("final_score", sa.Float(), nullable=False),
            sa.Column("bottom_line_passed", sa.Boolean(), nullable=False),
            sa.Column("bottom_line_report", sa.JSON(), nullable=False),
            sa.Column("llm_explanation", sa.Text(), nullable=False),
            sa.Column("evidence_pack", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["proposal_id"], ["strategy_proposals.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("decision_id"),
        )
        op.create_index(op.f("ix_risk_decisions_action"), "risk_decisions", ["action"], unique=False)
        op.create_index(op.f("ix_risk_decisions_decision_id"), "risk_decisions", ["decision_id"], unique=True)
        op.create_index(op.f("ix_risk_decisions_proposal_id"), "risk_decisions", ["proposal_id"], unique=False)
        op.create_index(op.f("ix_risk_decisions_run_id"), "risk_decisions", ["run_id"], unique=False)

    if "audit_records" not in existing_tables:
        op.create_table(
            "audit_records",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("run_id", sa.String(length=64), nullable=False),
            sa.Column("decision_id", sa.String(length=64), nullable=False),
            sa.Column("event_type", sa.String(length=64), nullable=False),
            sa.Column("entity_type", sa.String(length=64), nullable=False),
            sa.Column("entity_id", sa.String(length=64), nullable=False),
            sa.Column("strategy_dsl_hash", sa.String(length=64), nullable=False),
            sa.Column("market_snapshot_hash", sa.String(length=64), nullable=False),
            sa.Column("event_digest_hash", sa.String(length=64), nullable=False),
            sa.Column("code_version", sa.String(length=64), nullable=False),
            sa.Column("config_version", sa.String(length=64), nullable=False),
            sa.Column("payload", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_audit_records_decision_id"), "audit_records", ["decision_id"], unique=False)
        op.create_index(op.f("ix_audit_records_event_type"), "audit_records", ["event_type"], unique=False)
        op.create_index(op.f("ix_audit_records_run_id"), "audit_records", ["run_id"], unique=False)

    if "runtime_settings" not in existing_tables:
        op.create_table(
            "runtime_settings",
            sa.Column("key", sa.String(length=64), nullable=False),
            sa.Column("value_json", sa.JSON(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("key"),
        )


def downgrade() -> None:
    op.drop_index(op.f("ix_audit_records_run_id"), table_name="audit_records")
    op.drop_index(op.f("ix_audit_records_event_type"), table_name="audit_records")
    op.drop_index(op.f("ix_audit_records_decision_id"), table_name="audit_records")
    op.drop_table("audit_records")

    op.drop_table("runtime_settings")

    op.drop_index(op.f("ix_risk_decisions_run_id"), table_name="risk_decisions")
    op.drop_index(op.f("ix_risk_decisions_proposal_id"), table_name="risk_decisions")
    op.drop_index(op.f("ix_risk_decisions_decision_id"), table_name="risk_decisions")
    op.drop_index(op.f("ix_risk_decisions_action"), table_name="risk_decisions")
    op.drop_table("risk_decisions")

    op.drop_index(op.f("ix_daily_event_digests_trade_date"), table_name="daily_event_digests")
    op.drop_index(op.f("ix_daily_event_digests_digest_hash"), table_name="daily_event_digests")
    op.drop_table("daily_event_digests")

    op.drop_index(op.f("ix_event_records_published_at"), table_name="event_records")
    op.drop_index(op.f("ix_event_records_event_type"), table_name="event_records")
    op.drop_index(op.f("ix_event_records_event_id"), table_name="event_records")
    op.drop_table("event_records")

    op.drop_index(op.f("ix_run_metric_snapshots_run_type"), table_name="run_metric_snapshots")
    op.drop_index(op.f("ix_run_metric_snapshots_run_id"), table_name="run_metric_snapshots")
    op.drop_table("run_metric_snapshots")

    op.drop_table("strategy_snapshots")

    op.drop_index(op.f("ix_experiment_runs_symbol"), table_name="experiment_runs")
    op.drop_index(op.f("ix_experiment_runs_strategy_name"), table_name="experiment_runs")
    op.drop_index(op.f("ix_experiment_runs_status"), table_name="experiment_runs")
    op.drop_index(op.f("ix_experiment_runs_proposal_id"), table_name="experiment_runs")
    op.drop_index(op.f("ix_experiment_runs_kind"), table_name="experiment_runs")
    op.drop_index("idx_experiment_runs_created_at", table_name="experiment_runs")
    op.drop_table("experiment_runs")

    op.drop_index(op.f("ix_backtest_runs_symbol"), table_name="backtest_runs")
    op.drop_index(op.f("ix_backtest_runs_strategy_name"), table_name="backtest_runs")
    op.drop_index(op.f("ix_backtest_runs_status"), table_name="backtest_runs")
    op.drop_index(op.f("ix_backtest_runs_proposal_id"), table_name="backtest_runs")
    op.drop_index("idx_backtest_runs_created_at", table_name="backtest_runs")
    op.drop_table("backtest_runs")

    op.drop_index(op.f("ix_strategy_proposals_status"), table_name="strategy_proposals")
    op.drop_index(op.f("ix_strategy_proposals_symbol"), table_name="strategy_proposals")
    op.drop_index(op.f("ix_strategy_proposals_run_id"), table_name="strategy_proposals")
    op.drop_table("strategy_proposals")

    event_type_enum.drop(op.get_bind(), checkfirst=True)
    risk_action_enum.drop(op.get_bind(), checkfirst=True)
    proposal_status_enum.drop(op.get_bind(), checkfirst=True)
    experiment_kind_enum.drop(op.get_bind(), checkfirst=True)
    run_status_enum.drop(op.get_bind(), checkfirst=True)
