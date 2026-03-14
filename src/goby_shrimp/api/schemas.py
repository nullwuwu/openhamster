from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from .models import EventType, ExperimentKind, ProposalStatus, RiskDecisionAction, RunStatus


class BacktestRunCreate(BaseModel):
    symbol: str = Field(default="2800.HK", min_length=1, max_length=32)
    strategy_name: str = Field(default="ma_cross", min_length=1, max_length=64)
    provider_name: str = Field(default="stooq", min_length=1, max_length=64)
    start_date: str = "2020-01-01"
    end_date: str | None = None
    initial_capital: float = 100000
    is_first_live: bool = False
    strategy_params: dict[str, Any] = Field(default_factory=dict)


class ExperimentRunCreate(BaseModel):
    symbol: str = Field(default="2800.HK", min_length=1, max_length=32)
    strategy_name: str = Field(default="ma_cross", min_length=1, max_length=64)
    provider_name: str = Field(default="stooq", min_length=1, max_length=64)
    start_date: str = "2020-01-01"
    end_date: str = "2025-01-01"
    top_n: int = 10
    train_months: int = 12
    test_months: int = 3
    step_months: int = 3


class RunMetricSnapshotDTO(BaseModel):
    cagr: float | None = None
    max_drawdown: float | None = None
    sharpe: float | None = None
    annual_turnover: float | None = None
    data_years: float | None = None
    metadata_payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class BacktestRunDTO(BaseModel):
    id: str
    symbol: str
    strategy_name: str
    provider_name: str
    status: RunStatus
    request_payload: dict[str, Any]
    response_payload: dict[str, Any] | None = None
    error_message: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    updated_at: datetime
    metrics: list[RunMetricSnapshotDTO] = Field(default_factory=list)


class ExperimentRunDTO(BaseModel):
    id: str
    kind: ExperimentKind
    symbol: str
    strategy_name: str
    provider_name: str
    status: RunStatus
    request_payload: dict[str, Any]
    response_payload: dict[str, Any] | None = None
    error_message: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    updated_at: datetime
    metrics: list[RunMetricSnapshotDTO] = Field(default_factory=list)


class StrategySnapshotDTO(BaseModel):
    strategy_name: str
    description: str
    enabled: bool
    default_params: dict[str, Any]
    tags: list[str] = Field(default_factory=list)
    supported_markets: list[str] = Field(default_factory=list)
    market_bias: str = 'balanced'
    updated_at: datetime


class PaperNavPointDTO(BaseModel):
    trade_date: str
    cash: float
    position_value: float
    total_equity: float


class PaperOrderDTO(BaseModel):
    id: int
    symbol: str
    side: str
    quantity: int
    price: float
    amount: float
    status: str
    created_at: str


class PaperPositionDTO(BaseModel):
    id: int
    symbol: str
    quantity: int
    avg_cost: float
    market_value: float
    updated_at: str


class PaperExecutionDTO(BaseModel):
    status: str
    executed_at: str | None = None
    reason: str | None = None
    signal: str | None = None
    target_quantity: int | None = None
    current_quantity: int | None = None
    order_side: str | None = None
    order_quantity: int | None = None
    latest_price: float | None = None
    latest_price_as_of: str | None = None
    price_age_hours: float | None = None
    price_changed: bool = False
    equity_changed: bool = False
    rebalance_triggered: bool = False
    explanation_key: str | None = None
    explanation: str | None = None
    cash: float | None = None
    position_value: float | None = None
    total_equity: float | None = None
    message: str | None = None


class PaperTradingDTO(BaseModel):
    nav: list[PaperNavPointDTO] = Field(default_factory=list)
    orders: list[PaperOrderDTO] = Field(default_factory=list)
    positions: list[PaperPositionDTO] = Field(default_factory=list)
    latest_execution: PaperExecutionDTO | None = None


class CreatedRunResponse(BaseModel):
    run_id: str
    status: Literal["queued"]


class EventRecordDTO(BaseModel):
    id: str
    event_id: str
    event_type: EventType
    market_scope: str
    symbol_scope: str
    published_at: datetime
    source: str
    title: str
    body_ref: str | None = None
    tags: list[str] = Field(default_factory=list)
    importance: float
    sentiment_hint: float
    metadata_payload: dict[str, Any] = Field(default_factory=dict)


class DailyEventDigestDTO(BaseModel):
    trade_date: str
    market_scope: str
    symbol_scope: str
    macro_summary: str
    event_scores: dict[str, Any] = Field(default_factory=dict)
    digest_hash: str
    event_ids: list[str] = Field(default_factory=list)


class MacroPipelineStatusDTO(BaseModel):
    provider: str
    active_provider: str | None = None
    provider_chain: list[str] = Field(default_factory=list)
    status: str
    message: str
    degraded: bool
    last_success_at: str | None = None
    fallback_mode: str | None = None
    fallback_event_count: int | None = None
    using_last_known_context: bool = False
    reliability_score: float | None = None
    reliability_tier: str | None = None
    freshness_hours: float | None = None
    freshness_tier: str | None = None
    health_score_30d: float | None = None
    degraded_count_30d: int | None = None
    fallback_count_30d: int | None = None
    recovery_count_30d: int | None = None


class MarketProfileDTO(BaseModel):
    market_scope: str
    label: str
    timezone: str
    benchmark_symbol: str
    trading_style: str
    structure_notes: list[str] = Field(default_factory=list)
    preferred_baseline_tags: list[str] = Field(default_factory=list)
    discouraged_baseline_tags: list[str] = Field(default_factory=list)
    execution_constraints: list[str] = Field(default_factory=list)
    governance: dict[str, Any] = Field(default_factory=dict)


class UniverseCandidateDTO(BaseModel):
    rank: int | None = None
    symbol: str
    name: str
    latest_price: float | None = None
    change_pct: float | None = None
    amplitude_pct: float | None = None
    return_20d_pct: float | None = None
    return_60d_pct: float | None = None
    volatility_20d_pct: float | None = None
    turnover_millions: float | None = None
    lot_cost_hkd: float | None = None
    affordability_ratio: float | None = None
    score: float | None = None
    factor_scores: dict[str, float] = Field(default_factory=dict)
    reason_tags: list[str] = Field(default_factory=list)
    selection_reason: str | None = None
    source: str


class UniverseSelectionDTO(BaseModel):
    mode: str
    market_scope: str
    selected_symbol: str
    source: str
    generated_at: str | None = None
    selection_reason: str | None = None
    top_factors: list[str] = Field(default_factory=list)
    candidate_count: int = 0
    top_n_limit: int | None = None
    min_turnover_millions: float | None = None
    account_capital_hkd: float | None = None
    max_lot_cost_ratio: float | None = None
    benchmark_symbol: str | None = None
    benchmark_gap: float | None = None
    benchmark_candidate: UniverseCandidateDTO | None = None
    candidates: list[UniverseCandidateDTO] = Field(default_factory=list)


class MarketSnapshotDTO(BaseModel):
    regime: str
    confidence: float
    summary: str
    market_snapshot_hash: str
    symbol: str
    price_context: dict[str, Any] = Field(default_factory=dict)
    event_lane_sources: dict[str, str] = Field(default_factory=dict)
    market_profile: MarketProfileDTO
    universe_selection: UniverseSelectionDTO
    macro_status: MacroPipelineStatusDTO
    event_digest: DailyEventDigestDTO
    event_stream_preview: list[EventRecordDTO] = Field(default_factory=list)


class DebateReportDTO(BaseModel):
    stance_for: list[str] = Field(default_factory=list)
    stance_against: list[str] = Field(default_factory=list)
    synthesis: str


class EvidencePackDTO(BaseModel):
    bottom_line_report: dict[str, Any] = Field(default_factory=dict)
    deterministic_evidence: dict[str, Any] = Field(default_factory=dict)
    governance_report: dict[str, Any] = Field(default_factory=dict)
    quality_report: dict[str, Any] = Field(default_factory=dict)
    llm_judgment_inputs: dict[str, Any] = Field(default_factory=dict)


class StrategyProposalDTO(BaseModel):
    id: str
    run_id: str
    title: str
    symbol: str
    market_scope: str
    thesis: str
    source_kind: str
    provider_status: str
    provider_model: str
    provider_message: str
    market_snapshot_hash: str
    event_digest_hash: str
    strategy_dsl: dict[str, Any] = Field(default_factory=dict)
    debate_report: DebateReportDTO
    evidence_pack: EvidencePackDTO
    features_used: list[str] = Field(default_factory=list)
    deterministic_score: float
    llm_score: float
    final_score: float
    status: ProposalStatus
    created_at: datetime
    updated_at: datetime
    promoted_at: datetime | None = None


class RiskDecisionDTO(BaseModel):
    id: str
    decision_id: str
    run_id: str
    proposal_id: str
    action: RiskDecisionAction
    deterministic_score: float
    llm_score: float
    final_score: float
    bottom_line_passed: bool
    bottom_line_report: dict[str, Any] = Field(default_factory=dict)
    llm_explanation: str
    evidence_pack: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class AuditRecordDTO(BaseModel):
    id: int
    run_id: str
    decision_id: str
    event_type: str
    entity_type: str
    entity_id: str
    strategy_dsl_hash: str
    market_snapshot_hash: str
    event_digest_hash: str
    code_version: str
    config_version: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class ActiveStrategyDTO(BaseModel):
    proposal: StrategyProposalDTO | None = None
    latest_decision: RiskDecisionDTO | None = None
    paper_trading: PaperTradingDTO
    operational_acceptance: dict[str, Any] = Field(default_factory=dict)


class CandidateStrategyDTO(BaseModel):
    proposal: StrategyProposalDTO
    latest_decision: RiskDecisionDTO | None = None


class LLMStatusDTO(BaseModel):
    provider: Literal["minimax", "mock"]
    model: str
    status: str
    message: str
    using_mock_fallback: bool
    configured_providers: list[Literal["minimax", "mock"]] = Field(default_factory=list)


class RuntimeLLMUpdate(BaseModel):
    provider: Literal["minimax", "mock"]


class PipelineRuntimeStatusDTO(BaseModel):
    current_state: str
    status_message: str
    current_stage: str | None = None
    stage_started_at: str | None = None
    stage_durations_ms: dict[str, int] = Field(default_factory=dict)
    last_run_at: str | None = None
    last_success_at: str | None = None
    last_failure_at: str | None = None
    consecutive_failures: int = 0
    expected_next_run_at: str | None = None
    last_duration_ms: int | None = None
    last_trigger: str | None = None
    degraded: bool = False
    stalled: bool = False
    process_started_at: str | None = None
    process_uptime_seconds: int | None = None
    startup_mode: str | None = None
    local_logs_available: bool = False


class ProviderCohortDTO(BaseModel):
    provider: str
    cohort_started_at: str | None = None
    cohort_closed_at: str | None = None
    proposal_count: int = 0
    real_proposal_count: int = 0
    fallback_count: int = 0
    fallback_rate: float = 0.0
    promoted_count: int = 0
    promotion_rate: float = 0.0
    avg_final_score: float | None = None
    promoted_symbol_distribution: dict[str, int] = Field(default_factory=dict)


class ProviderMigrationSummaryDTO(BaseModel):
    comparison_window_days: int = 30
    current_provider: str
    current_cohort_started_at: str | None = None
    previous_provider: str | None = None
    switch_detected: bool = False
    summary: str
    notes: list[str] = Field(default_factory=list)
    current: ProviderCohortDTO
    previous: ProviderCohortDTO | None = None
    deltas: dict[str, float] = Field(default_factory=dict)


class ProviderCohortHistoryItemDTO(ProviderCohortDTO):
    label: str
    is_current: bool = False


class LiveReadinessDTO(BaseModel):
    status: str
    score: int
    summary: str
    approved_for_live: bool = False
    blockers: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    dimensions: dict[str, int] = Field(default_factory=dict)
    evidence: dict[str, Any] = Field(default_factory=dict)


class LiveReadinessHistoryItemDTO(LiveReadinessDTO):
    created_at: datetime


class LiveReadinessChangeDTO(BaseModel):
    trend: str
    score_delta: float
    added_blockers: list[str] = Field(default_factory=list)
    cleared_blockers: list[str] = Field(default_factory=list)
    linked_changes: list[str] = Field(default_factory=list)


class RuntimeLogDTO(BaseModel):
    stream: Literal["out", "err"]
    path: str | None = None
    exists: bool = False
    updated_at: datetime | None = None
    lines: list[str] = Field(default_factory=list)


class CommandCenterDTO(BaseModel):
    generated_at: datetime
    timezone: str
    llm_status: LLMStatusDTO
    runtime_status: PipelineRuntimeStatusDTO
    provider_migration: ProviderMigrationSummaryDTO
    provider_migration_history: list[ProviderCohortHistoryItemDTO] = Field(default_factory=list)
    live_readiness: LiveReadinessDTO
    live_readiness_history: list[LiveReadinessHistoryItemDTO] = Field(default_factory=list)
    live_readiness_change: LiveReadinessChangeDTO | None = None
    market_snapshot: MarketSnapshotDTO
    active_strategy: ActiveStrategyDTO
    candidate_count: int
    latest_risk_decision: RiskDecisionDTO | None = None
    latest_audit_events: list[AuditRecordDTO] = Field(default_factory=list)
    latest_event_digest: DailyEventDigestDTO


class AcceptanceReportDTO(BaseModel):
    generated_at: datetime
    window_days: int
    status: str
    strategy_title: str | None = None
    key_findings: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    quality: dict[str, Any] = Field(default_factory=dict)
    operations: dict[str, Any] = Field(default_factory=dict)
    macro: dict[str, Any] = Field(default_factory=dict)
    governance: dict[str, Any] = Field(default_factory=dict)
