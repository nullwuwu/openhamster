from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import uuid4

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class RunStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ExperimentKind(str, Enum):
    OPTIMIZER = "optimizer"
    WALKFORWARD = "walkforward"


class ProposalStatus(str, Enum):
    CANDIDATE = "candidate"
    ACTIVE = "active"
    REJECTED = "rejected"
    ARCHIVED = "archived"


class RiskDecisionAction(str, Enum):
    REJECT = "reject"
    KEEP_CANDIDATE = "keep_candidate"
    PROMOTE_TO_PAPER = "promote_to_paper"
    PAUSE_ACTIVE = "pause_active"
    ROLLBACK_TO_PREVIOUS_STABLE = "rollback_to_previous_stable"


class EventType(str, Enum):
    MACRO = "macro"


class BacktestRun(Base):
    __tablename__ = "backtest_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    strategy_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    provider_name: Mapped[str] = mapped_column(String(64), nullable=False)
    proposal_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("strategy_proposals.id"), nullable=True, index=True)
    status: Mapped[RunStatus] = mapped_column(SqlEnum(RunStatus), nullable=False, default=RunStatus.QUEUED)
    request_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    response_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    metric_snapshots: Mapped[list[RunMetricSnapshot]] = relationship(
        "RunMetricSnapshot",
        back_populates="backtest_run",
        cascade="all, delete-orphan",
    )

    __table_args__ = (Index("idx_backtest_runs_created_at", "created_at"),)


class ExperimentRun(Base):
    __tablename__ = "experiment_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    kind: Mapped[ExperimentKind] = mapped_column(SqlEnum(ExperimentKind), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    strategy_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    provider_name: Mapped[str] = mapped_column(String(64), nullable=False)
    proposal_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("strategy_proposals.id"), nullable=True, index=True)
    status: Mapped[RunStatus] = mapped_column(SqlEnum(RunStatus), nullable=False, default=RunStatus.QUEUED)
    request_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    response_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    metric_snapshots: Mapped[list[RunMetricSnapshot]] = relationship(
        "RunMetricSnapshot",
        back_populates="experiment_run",
        cascade="all, delete-orphan",
    )

    __table_args__ = (Index("idx_experiment_runs_created_at", "created_at"),)


class RunMetricSnapshot(Base):
    __tablename__ = "run_metric_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    cagr: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_drawdown: Mapped[float | None] = mapped_column(Float, nullable=True)
    sharpe: Mapped[float | None] = mapped_column(Float, nullable=True)
    annual_turnover: Mapped[float | None] = mapped_column(Float, nullable=True)
    data_years: Mapped[float | None] = mapped_column(Float, nullable=True)
    metadata_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    backtest_run_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("backtest_runs.id", ondelete="CASCADE"),
        nullable=True,
    )
    experiment_run_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("experiment_runs.id", ondelete="CASCADE"),
        nullable=True,
    )

    backtest_run: Mapped[BacktestRun | None] = relationship("BacktestRun", back_populates="metric_snapshots")
    experiment_run: Mapped[ExperimentRun | None] = relationship("ExperimentRun", back_populates="metric_snapshots")


class StrategySnapshot(Base):
    __tablename__ = "strategy_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    strategy_name: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    default_params: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    enabled: Mapped[bool] = mapped_column(nullable=False, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (UniqueConstraint("strategy_name", name="uq_strategy_snapshots_name"),)


class EventRecord(Base):
    __tablename__ = "event_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    event_id: Mapped[str] = mapped_column(String(96), nullable=False, unique=True, index=True)
    event_type: Mapped[EventType] = mapped_column(SqlEnum(EventType), nullable=False, index=True)
    market_scope: Mapped[str] = mapped_column(String(16), nullable=False, default="HK", index=True)
    symbol_scope: Mapped[str] = mapped_column(String(32), nullable=False, default="*")
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    body_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    importance: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    sentiment_hint: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    metadata_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DailyEventDigest(Base):
    __tablename__ = "daily_event_digests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trade_date: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    market_scope: Mapped[str] = mapped_column(String(16), nullable=False, default="HK")
    symbol_scope: Mapped[str] = mapped_column(String(32), nullable=False, default="*")
    macro_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    event_scores: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    digest_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    event_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (UniqueConstraint("trade_date", "market_scope", "symbol_scope", name="uq_daily_digest_scope"),)


class StrategyProposal(Base):
    __tablename__ = "strategy_proposals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    run_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    market_scope: Mapped[str] = mapped_column(String(16), nullable=False, default="HK")
    thesis: Mapped[str] = mapped_column(Text, nullable=False)
    source_kind: Mapped[str] = mapped_column(String(32), nullable=False, default="llm")
    provider_status: Mapped[str] = mapped_column(String(32), nullable=False, default="mock")
    provider_model: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    provider_message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    market_snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    event_digest_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    strategy_dsl: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    debate_report: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    evidence_pack: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    features_used: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    deterministic_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    llm_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    final_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    status: Mapped[ProposalStatus] = mapped_column(SqlEnum(ProposalStatus), nullable=False, default=ProposalStatus.CANDIDATE, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    promoted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    decisions: Mapped[list[RiskDecision]] = relationship(
        "RiskDecision",
        back_populates="proposal",
        cascade="all, delete-orphan",
    )


class RiskDecision(Base):
    __tablename__ = "risk_decisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    decision_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    run_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    proposal_id: Mapped[str] = mapped_column(String(36), ForeignKey("strategy_proposals.id", ondelete="CASCADE"), nullable=False, index=True)
    action: Mapped[RiskDecisionAction] = mapped_column(SqlEnum(RiskDecisionAction), nullable=False, index=True)
    deterministic_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    llm_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    final_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    bottom_line_passed: Mapped[bool] = mapped_column(nullable=False, default=False)
    bottom_line_report: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    llm_explanation: Mapped[str] = mapped_column(Text, nullable=False, default="")
    evidence_pack: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    proposal: Mapped[StrategyProposal] = relationship("StrategyProposal", back_populates="decisions")


class AuditRecord(Base):
    __tablename__ = "audit_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    decision_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False)
    strategy_dsl_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    market_snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    event_digest_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    code_version: Mapped[str] = mapped_column(String(64), nullable=False, default="local")
    config_version: Mapped[str] = mapped_column(String(64), nullable=False, default="v1.3")
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RuntimeSetting(Base):
    __tablename__ = "runtime_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
