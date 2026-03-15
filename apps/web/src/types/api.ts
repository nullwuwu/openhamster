export type RunStatus = 'queued' | 'running' | 'succeeded' | 'failed'
export type ProposalStatus = 'candidate' | 'active' | 'rejected' | 'archived'
export type RiskDecisionAction =
  | 'reject'
  | 'keep_candidate'
  | 'promote_to_paper'
  | 'pause_active'
  | 'rollback_to_previous_stable'
export type EventType = 'macro'
export type LLMProvider = 'minimax' | 'mock'

export interface RunMetricSnapshot {
  cagr: number | null
  max_drawdown: number | null
  sharpe: number | null
  annual_turnover: number | null
  data_years: number | null
  metadata_payload: Record<string, unknown>
  created_at: string
}

export interface BacktestRun {
  id: string
  symbol: string
  strategy_name: string
  provider_name: string
  status: RunStatus
  request_payload: Record<string, unknown>
  response_payload?: Record<string, unknown>
  error_message?: string
  created_at: string
  started_at?: string
  finished_at?: string
  updated_at: string
  metrics: RunMetricSnapshot[]
}

export interface ExperimentRun {
  id: string
  kind: 'optimizer' | 'walkforward'
  symbol: string
  strategy_name: string
  provider_name: string
  status: RunStatus
  request_payload: Record<string, unknown>
  response_payload?: Record<string, unknown>
  error_message?: string
  created_at: string
  started_at?: string
  finished_at?: string
  updated_at: string
  metrics: RunMetricSnapshot[]
}

export interface StrategySnapshot {
  strategy_name: string
  description: string
  enabled: boolean
  default_params: Record<string, unknown>
  tags: string[]
  supported_markets: string[]
  market_bias: string
  updated_at: string
}

export interface EventRecord {
  id: string
  event_id: string
  event_type: EventType
  market_scope: string
  symbol_scope: string
  published_at: string
  source: string
  title: string
  body_ref?: string
  tags: string[]
  importance: number
  sentiment_hint: number
  metadata_payload: Record<string, unknown>
}

export interface DailyEventDigest {
  trade_date: string
  market_scope: string
  symbol_scope: string
  macro_summary: string
  event_scores: Record<string, number>
  digest_hash: string
  event_ids: string[]
}

export interface MacroPipelineStatus {
  provider: string
  active_provider?: string
  provider_chain?: string[]
  status: string
  message: string
  degraded: boolean
  last_success_at?: string
  fallback_mode?: string
  fallback_event_count?: number
  using_last_known_context?: boolean
  reliability_score?: number
  reliability_tier?: string
  freshness_hours?: number
  freshness_tier?: string
  health_score_30d?: number
  degraded_count_30d?: number
  fallback_count_30d?: number
  recovery_count_30d?: number
}

export interface MarketProfile {
  market_scope: string
  label: string
  timezone: string
  benchmark_symbol: string
  trading_style: string
  structure_notes: string[]
  preferred_baseline_tags: string[]
  discouraged_baseline_tags: string[]
  execution_constraints: string[]
  governance: Record<string, unknown>
}

export interface UniverseCandidate {
  rank?: number | null
  symbol: string
  name: string
  latest_price?: number | null
  change_pct?: number | null
  amplitude_pct?: number | null
  return_20d_pct?: number | null
  return_60d_pct?: number | null
  volatility_20d_pct?: number | null
  turnover_millions?: number | null
  lot_cost_hkd?: number | null
  affordability_ratio?: number | null
  score?: number | null
  factor_scores?: Record<string, number>
  reason_tags?: string[]
  selection_reason?: string | null
  source: string
}

export interface UniverseSelection {
  mode: string
  market_scope: string
  selected_symbol: string
  source: string
  generated_at?: string | null
  selection_reason?: string | null
  top_factors?: string[]
  candidate_count?: number
  top_n_limit?: number | null
  min_turnover_millions?: number | null
  account_capital_hkd?: number | null
  max_lot_cost_ratio?: number | null
  benchmark_symbol?: string | null
  benchmark_gap?: number | null
  benchmark_candidate?: UniverseCandidate | null
  candidates: UniverseCandidate[]
}

export interface MarketSnapshot {
  regime: string
  confidence: number
  summary: string
  market_snapshot_hash: string
  symbol: string
  price_context: Record<string, unknown>
  event_lane_sources: Record<string, string>
  market_profile: MarketProfile
  universe_selection: UniverseSelection
  macro_status: MacroPipelineStatus
  event_digest: DailyEventDigest
  event_stream_preview: EventRecord[]
}

export interface DebateReport {
  stance_for: string[]
  stance_against: string[]
  synthesis: string
}

export interface GovernanceReport {
  version?: string
  market_profile?: Record<string, unknown>
  thresholds?: Record<string, unknown>
  promotion_gate?: {
    eligible?: boolean
    blocked_reasons?: string[]
  }
  active_comparison?: {
    active_title?: string | null
    active_score?: number | null
    score_delta?: number | null
    can_challenge_active?: boolean
    cooldown_remaining_days?: number
  }
  macro_dependency?: Record<string, unknown>
  active_health?: Record<string, unknown>
  lifecycle?: {
    phase?: string
    next_step?: string
    rechallenge_allowed?: boolean
    review_trigger?: string
    eta_kind?: string
    estimated_next_eligible_at?: string | null
    resume_conditions?: string[]
  }
  selected_action?: string
}

export interface QualityReport {
  version?: string
  oos_validation?: {
    walkforward_pass_rate?: number
    required_pass_rate?: number
    passed?: boolean
    passed_windows?: number
    total_windows?: number
    stability_ratio?: number
  }
  pool_comparison?: {
    active_title?: string | null
    score_delta?: number | null
    required_delta?: number
    comparable?: boolean
    replaceable?: boolean
    relative_to_active?: string
  }
  robustness?: {
    param_sensitivity?: number
    max_allowed?: number
    passed?: boolean
  }
  return_quality?: {
    cagr?: number
    sharpe?: number
    max_drawdown?: number
  }
  backtest_gate?: {
    available?: boolean
    eligible_for_paper?: boolean
    blocked_reasons?: string[]
    summary?: string
    review?: Record<string, unknown>
    metrics?: Record<string, unknown>
    window?: Record<string, unknown>
  }
  verdict?: {
    quality_band?: string
    comparable?: boolean
    replaceable?: boolean
    accumulable?: boolean
  }
  pool_ranking?: {
    rank?: number
    total_tracked?: number
    leader_score?: number
    leader_gap?: number
    percentile?: number
    median_score?: number
    median_gap?: number
    selection_state?: string
  }
  track_record?: {
    recent_total?: number
    recent_comparable?: number
    recent_replaceable?: number
    recent_30d_total?: number
    recent_30d_comparable?: number
    window_days?: number
    comparable_ratio?: number
    replaceable_ratio?: number
    average_final_score?: number
    best_final_score?: number
    average_stability_ratio?: number
    stable_streak?: number
    trend?: string
  }
}

export interface EvidencePack {
  bottom_line_report: Record<string, boolean>
  deterministic_evidence: Record<string, number | string | boolean>
  governance_report?: GovernanceReport
  quality_report?: QualityReport
  llm_judgment_inputs: Record<string, unknown>
}

export interface StrategyProposal {
  id: string
  run_id: string
  title: string
  symbol: string
  market_scope: string
  thesis: string
  source_kind: string
  provider_status: string
  provider_model: string
  provider_message: string
  market_snapshot_hash: string
  event_digest_hash: string
  strategy_dsl: Record<string, unknown>
  debate_report: DebateReport
  evidence_pack: EvidencePack
  features_used: string[]
  deterministic_score: number
  llm_score: number
  final_score: number
  status: ProposalStatus
  created_at: string
  updated_at: string
  promoted_at?: string
}

export interface RiskDecision {
  id: string
  decision_id: string
  run_id: string
  proposal_id: string
  action: RiskDecisionAction
  deterministic_score: number
  llm_score: number
  final_score: number
  bottom_line_passed: boolean
  bottom_line_report: Record<string, boolean>
  llm_explanation: string
  evidence_pack: EvidencePack
  created_at: string
}

export interface AuditRecord {
  id: number
  run_id: string
  decision_id: string
  event_type: string
  entity_type: string
  entity_id: string
  strategy_dsl_hash: string
  market_snapshot_hash: string
  event_digest_hash: string
  code_version: string
  config_version: string
  payload: Record<string, unknown>
  created_at: string
}

export interface PaperNavPoint {
  trade_date: string
  cash: number
  position_value: number
  total_equity: number
}

export interface PaperOrder {
  id: number
  symbol: string
  side: string
  quantity: number
  price: number
  amount: number
  status: string
  created_at: string
}

export interface PaperPosition {
  id: number
  symbol: string
  quantity: number
  avg_cost: number
  market_value: number
  updated_at: string
}

export interface PaperExecution {
  status: string
  executed_at?: string | null
  reason?: string | null
  signal?: string | null
  target_quantity?: number | null
  current_quantity?: number | null
  order_side?: string | null
  order_quantity?: number | null
  latest_price?: number | null
  latest_price_as_of?: string | null
  price_age_hours?: number | null
  price_changed?: boolean
  equity_changed?: boolean
  rebalance_triggered?: boolean
  explanation_key?: string | null
  explanation?: string | null
  cash?: number | null
  position_value?: number | null
  total_equity?: number | null
  message?: string | null
}

export interface PaperTrading {
  nav: PaperNavPoint[]
  orders: PaperOrder[]
  positions: PaperPosition[]
  latest_execution?: PaperExecution | null
}

export interface ActiveStrategy {
  proposal: StrategyProposal | null
  latest_decision: RiskDecision | null
  paper_trading: PaperTrading
  operational_acceptance?: Record<string, unknown>
}

export interface AcceptanceReport {
  generated_at: string
  window_days: number
  status: string
  strategy_title?: string | null
  key_findings: string[]
  next_actions: string[]
  quality: Record<string, unknown>
  operations: Record<string, unknown>
  macro: Record<string, unknown>
  governance: Record<string, unknown>
}

export interface CandidateStrategy {
  proposal: StrategyProposal
  latest_decision: RiskDecision | null
}

export interface LLMStatus {
  provider: LLMProvider
  model: string
  status: string
  message: string
  using_mock_fallback: boolean
  configured_providers: LLMProvider[]
}

export interface PipelineRuntimeStatus {
  current_state: string
  status_message: string
  current_stage?: string
  stage_started_at?: string
  stage_durations_ms: Record<string, number>
  last_run_at?: string
  last_success_at?: string
  last_failure_at?: string
  consecutive_failures: number
  expected_next_run_at?: string
  last_duration_ms?: number
  last_trigger?: string
  degraded: boolean
  stalled: boolean
  process_started_at?: string
  process_uptime_seconds?: number
  startup_mode?: string
  local_logs_available: boolean
}

export interface RuntimeSyncHistoryItem {
  created_at: string
  state: string
  trigger?: string | null
  total_duration_ms?: number | null
  stage_durations_ms: Record<string, number>
  current_stage?: string | null
  status_message?: string | null
  degraded: boolean
}

export interface ProviderCohort {
  provider: string
  cohort_started_at?: string | null
  cohort_closed_at?: string | null
  proposal_count: number
  real_proposal_count: number
  fallback_count: number
  fallback_rate: number
  promoted_count: number
  promotion_rate: number
  avg_final_score?: number | null
  promoted_symbol_distribution: Record<string, number>
}

export interface ProviderMigrationSummary {
  comparison_window_days: number
  current_provider: string
  current_cohort_started_at?: string | null
  previous_provider?: string | null
  switch_detected: boolean
  summary: string
  notes: string[]
  current: ProviderCohort
  previous?: ProviderCohort | null
  deltas: Record<string, number>
}

export interface ProviderCohortHistoryItem extends ProviderCohort {
  label: string
  is_current: boolean
}

export interface LiveReadiness {
  status: string
  score: number
  summary: string
  approved_for_live: boolean
  blockers: string[]
  next_actions: string[]
  dimensions: Record<string, number>
  evidence: Record<string, unknown>
}

export interface LiveReadinessHistoryItem extends LiveReadiness {
  created_at: string
}

export interface LiveReadinessChange {
  trend: string
  score_delta: number
  added_blockers: string[]
  cleared_blockers: string[]
  linked_changes: string[]
}

export interface RuntimeLog {
  stream: 'out' | 'err'
  path?: string | null
  exists: boolean
  updated_at?: string | null
  lines: string[]
}

export interface CommandCenter {
  generated_at: string
  timezone: string
  llm_status: LLMStatus
  runtime_status: PipelineRuntimeStatus
  runtime_sync_history: RuntimeSyncHistoryItem[]
  provider_migration: ProviderMigrationSummary
  provider_migration_history: ProviderCohortHistoryItem[]
  live_readiness: LiveReadiness
  live_readiness_history: LiveReadinessHistoryItem[]
  live_readiness_change: LiveReadinessChange | null
  market_snapshot: MarketSnapshot
  active_strategy: ActiveStrategy
  candidate_count: number
  latest_risk_decision: RiskDecision | null
  latest_audit_events: AuditRecord[]
  latest_event_digest: DailyEventDigest
}

export interface TriggerSyncResponse extends PipelineRuntimeStatus {}
