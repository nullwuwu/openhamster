from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from collections import deque

from fastapi import APIRouter, BackgroundTasks, Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..runtime import build_pipeline_scheduler
from ..strategy import get_strategy_registry
from .db import SessionLocal, get_db, init_database
from .models import BacktestRun, ExperimentRun, RunStatus, StrategyProposal, StrategySnapshot
from .schemas import (
    ActiveStrategyDTO,
    AcceptanceReportDTO,
    AuditRecordDTO,
    BacktestRunCreate,
    BacktestRunDTO,
    CandidateStrategyDTO,
    CommandCenterDTO,
    CreatedRunResponse,
    DailyEventDigestDTO,
    EventRecordDTO,
    ExperimentRunCreate,
    ExperimentRunDTO,
    LLMStatusDTO,
    KnowledgeSourceDTO,
    KnowledgeSuggestionDTO,
    LiveReadinessChangeDTO,
    LiveReadinessDTO,
    LiveReadinessHistoryItemDTO,
    MacroPipelineStatusDTO,
    MarketProfileDTO,
    MarketSnapshotDTO,
    UniverseCandidateDTO,
    UniverseSelectionDTO,
    PaperExecutionDTO,
    PaperNavPointDTO,
    PaperOrderDTO,
    PaperPositionDTO,
    PaperTradingDTO,
    PipelineRuntimeStatusDTO,
    RuntimeSyncHistoryItemDTO,
    ProviderCohortDTO,
    ProviderCohortHistoryItemDTO,
    ProviderMigrationSummaryDTO,
    ResearchBatchDTO,
    RiskDecisionDTO,
    RuntimeLogDTO,
    RuntimeLLMUpdate,
    RunMetricSnapshotDTO,
    SlotFocusDTO,
    SlotGateDTO,
    PaperSummaryDTO,
    StrategyProposalDTO,
    StrategySnapshotDTO,
)
from .services import (
    build_acceptance_report,
    build_live_readiness,
    build_live_readiness_change,
    build_live_readiness_history,
    build_operational_acceptance,
    build_provider_migration_history,
    build_provider_migration_summary,
    build_runtime_sync_history,
    build_market_snapshot,
    execute_backtest_run,
    execute_experiment_run,
    fetch_paper_data,
    get_active_strategy,
    get_backtest_run_with_metrics,
    get_current_llm_status,
    get_knowledge_suggestion,
    get_latest_paper_execution,
    get_pipeline_runtime_status,
    get_research_batch,
    get_experiment_run_with_metrics,
    get_latest_risk_decision,
    get_strategy_proposal,
    list_audit_records,
    list_backtest_runs_with_metrics,
    list_candidate_strategies,
    list_event_digests,
    list_event_stream,
    list_experiment_runs_with_metrics,
    list_knowledge_sources,
    list_knowledge_suggestions,
    list_risk_decisions,
    list_research_batches,
    list_strategy_proposals,
    now_tz,
    set_runtime_llm_provider,
    sync_agent_state,
    sync_strategy_snapshots,
)

router = APIRouter(prefix="/api/v1")
logger = logging.getLogger(__name__)
REPO_ROOT = Path(__file__).resolve().parents[3]
FRONTEND_DIST_DIR = REPO_ROOT / "apps" / "web" / "dist"
LOG_DIR = REPO_ROOT / "logs"
RUNTIME_LOG_PATHS = {
    "out": LOG_DIR / "gobyshrimp-api.out.log",
    "err": LOG_DIR / "gobyshrimp-api.err.log",
}
PROCESS_STARTED_AT: datetime | None = None


def _run_sync_job(*, trigger: str, force_refresh: bool = True) -> None:
    with SessionLocal() as db:
        sync_agent_state(db, force_refresh=force_refresh, trigger=trigger)


def _run_manual_sync_job() -> None:
    _run_sync_job(trigger='manual_api', force_refresh=True)


def _run_runtime_provider_switch_sync_job() -> None:
    _run_sync_job(trigger='runtime_provider_switch', force_refresh=True)


def _run_startup_sync_job() -> None:
    _run_sync_job(trigger='startup', force_refresh=False)


def _to_metric_dto(items: list) -> list[RunMetricSnapshotDTO]:
    return [
        RunMetricSnapshotDTO(
            cagr=item.cagr,
            max_drawdown=item.max_drawdown,
            sharpe=item.sharpe,
            annual_turnover=item.annual_turnover,
            data_years=item.data_years,
            metadata_payload=item.metadata_payload,
            created_at=item.created_at,
        )
        for item in items
    ]


def _to_backtest_dto(run: BacktestRun) -> BacktestRunDTO:
    return BacktestRunDTO(
        id=run.id,
        symbol=run.symbol,
        strategy_name=run.strategy_name,
        provider_name=run.provider_name,
        status=run.status,
        request_payload=run.request_payload,
        response_payload=run.response_payload,
        error_message=run.error_message,
        created_at=run.created_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
        updated_at=run.updated_at,
        metrics=_to_metric_dto(run.metric_snapshots),
    )


def _to_experiment_dto(run: ExperimentRun) -> ExperimentRunDTO:
    return ExperimentRunDTO(
        id=run.id,
        kind=run.kind,
        symbol=run.symbol,
        strategy_name=run.strategy_name,
        provider_name=run.provider_name,
        status=run.status,
        request_payload=run.request_payload,
        response_payload=run.response_payload,
        error_message=run.error_message,
        created_at=run.created_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
        updated_at=run.updated_at,
        metrics=_to_metric_dto(run.metric_snapshots),
    )


def _to_paper_dto(limit: int = 100) -> PaperTradingDTO:
    paper = fetch_paper_data(limit=limit)
    return PaperTradingDTO(
        nav=[PaperNavPointDTO(**item) for item in paper["nav"]],
        orders=[PaperOrderDTO(**item) for item in paper["orders"]],
        positions=[PaperPositionDTO(**item) for item in paper["positions"]],
        latest_execution=None,
    )


def _to_digest_dto(record) -> DailyEventDigestDTO:
    return DailyEventDigestDTO(
        trade_date=record.trade_date,
        market_scope=record.market_scope,
        symbol_scope=record.symbol_scope,
        macro_summary=record.macro_summary,
        event_scores=record.event_scores,
        digest_hash=record.digest_hash,
        event_ids=record.event_ids,
    )


def _to_event_dto(record) -> EventRecordDTO:
    return EventRecordDTO(
        id=record.id,
        event_id=record.event_id,
        event_type=record.event_type,
        market_scope=record.market_scope,
        symbol_scope=record.symbol_scope,
        published_at=record.published_at,
        source=record.source,
        title=record.title,
        body_ref=record.body_ref,
        tags=record.tags,
        importance=record.importance,
        sentiment_hint=record.sentiment_hint,
        metadata_payload=record.metadata_payload,
    )


def _to_risk_decision_dto(record) -> RiskDecisionDTO:
    return RiskDecisionDTO(
        id=record.id,
        decision_id=record.decision_id,
        run_id=record.run_id,
        proposal_id=record.proposal_id,
        action=record.action,
        deterministic_score=record.deterministic_score,
        llm_score=record.llm_score,
        final_score=record.final_score,
        bottom_line_passed=record.bottom_line_passed,
        bottom_line_report=record.bottom_line_report,
        llm_explanation=record.llm_explanation,
        evidence_pack=record.evidence_pack,
        created_at=record.created_at,
    )


def _to_audit_dto(record) -> AuditRecordDTO:
    return AuditRecordDTO(
        id=record.id,
        run_id=record.run_id,
        decision_id=record.decision_id,
        event_type=record.event_type,
        entity_type=record.entity_type,
        entity_id=record.entity_id,
        strategy_dsl_hash=record.strategy_dsl_hash,
        market_snapshot_hash=record.market_snapshot_hash,
        event_digest_hash=record.event_digest_hash,
        code_version=record.code_version,
        config_version=record.config_version,
        payload=record.payload,
        created_at=record.created_at,
    )


def _to_proposal_dto(record: StrategyProposal) -> StrategyProposalDTO:
    return StrategyProposalDTO(
        id=record.id,
        run_id=record.run_id,
        title=record.title,
        symbol=record.symbol,
        market_scope=record.market_scope,
        thesis=record.thesis,
        source_kind=record.source_kind,
        provider_status=record.provider_status,
        provider_model=record.provider_model,
        provider_message=record.provider_message,
        market_snapshot_hash=record.market_snapshot_hash,
        event_digest_hash=record.event_digest_hash,
        strategy_dsl=record.strategy_dsl,
        debate_report=record.debate_report,
        evidence_pack=record.evidence_pack,
        features_used=record.features_used,
        deterministic_score=record.deterministic_score,
        llm_score=record.llm_score,
        final_score=record.final_score,
        status=record.status,
        created_at=record.created_at,
        updated_at=record.updated_at,
        promoted_at=record.promoted_at,
    )


def _to_market_snapshot_dto(db: Session) -> MarketSnapshotDTO:
    snapshot = build_market_snapshot(db)
    return MarketSnapshotDTO(
        regime=str(snapshot["regime"]),
        confidence=float(snapshot["confidence"]),
        summary=str(snapshot["summary"]),
        market_snapshot_hash=str(snapshot["market_snapshot_hash"]),
        symbol=str(snapshot["symbol"]),
        price_context=dict(snapshot["price_context"]),
        event_lane_sources={str(key): str(value) for key, value in dict(snapshot["event_lane_sources"]).items()},
        market_profile=MarketProfileDTO(**dict(snapshot["market_profile"])),
        macro_status=MacroPipelineStatusDTO(**dict(snapshot["macro_status"])),
        event_digest=_to_digest_dto(snapshot["event_digest"]),
        event_stream_preview=[_to_event_dto(record) for record in snapshot["event_stream_preview"]],
    )


def _to_llm_status_dto(status) -> LLMStatusDTO:
    return LLMStatusDTO(
        provider=status.provider,
        model=status.model,
        status=status.status,
        message=status.message,
        using_mock_fallback=status.using_mock_fallback,
        configured_providers=status.configured_providers,
    )


def _to_pipeline_runtime_status_dto(status: dict[str, object]) -> PipelineRuntimeStatusDTO:
    uptime_seconds = None
    if PROCESS_STARTED_AT is not None:
        uptime_seconds = max(0, int((now_tz() - PROCESS_STARTED_AT).total_seconds()))
    startup_mode = os.environ.get("GOBYSHRIMP_STARTUP_MODE", "manual")
    local_logs_available = any(path.exists() for path in RUNTIME_LOG_PATHS.values())
    return PipelineRuntimeStatusDTO(
        current_state=str(status.get('current_state', 'idle')),
        status_message=str(status.get('status_message', 'Pipeline status unavailable.')),
        current_stage=str(status['current_stage']) if status.get('current_stage') is not None else None,
        stage_started_at=status.get('stage_started_at'),
        stage_durations_ms={str(key): int(value) for key, value in dict(status.get('stage_durations_ms', {}) or {}).items()},
        last_run_at=status.get('last_run_at'),
        last_success_at=status.get('last_success_at'),
        last_failure_at=status.get('last_failure_at'),
        consecutive_failures=int(status.get('consecutive_failures', 0) or 0),
        expected_next_run_at=status.get('expected_next_run_at'),
        last_duration_ms=int(status['last_duration_ms']) if status.get('last_duration_ms') is not None else None,
        last_trigger=status.get('last_trigger'),
        degraded=bool(status.get('degraded', False)),
        stalled=bool(status.get('stalled', False)),
        process_started_at=PROCESS_STARTED_AT.isoformat() if PROCESS_STARTED_AT is not None else None,
        process_uptime_seconds=uptime_seconds,
        startup_mode=startup_mode,
        local_logs_available=local_logs_available,
        research_batch_size=int(status.get('research_batch_size', 0) or 0),
        research_symbols=[str(item) for item in list(status.get('research_symbols', []) or [])],
        research_symbol_states=[
            dict(item)
            for item in list(status.get('research_symbol_states', []) or [])
            if isinstance(item, dict)
        ],
        current_symbol=str(status.get('current_symbol')) if status.get('current_symbol') is not None else None,
        current_symbol_stage=str(status.get('current_symbol_stage')) if status.get('current_symbol_stage') is not None else None,
        batch_progress={str(key): int(value) for key, value in dict(status.get('batch_progress', {}) or {}).items()},
        current_batch_id=str(status.get('current_batch_id')) if status.get('current_batch_id') is not None else None,
        paper_slot_count=int(status.get('paper_slot_count', 1) or 1),
    )


def _to_provider_migration_summary_dto(summary: dict[str, object]) -> ProviderMigrationSummaryDTO:
    previous = dict(summary.get("previous", {}) or {})
    return ProviderMigrationSummaryDTO(
        comparison_window_days=int(summary.get("comparison_window_days", 30) or 30),
        current_provider=str(summary.get("current_provider", "mock")),
        current_cohort_started_at=summary.get("current_cohort_started_at"),
        previous_provider=str(previous.get("provider")) if previous.get("provider") is not None else None,
        switch_detected=bool(summary.get("switch_detected", False)),
        summary=str(summary.get("summary", "")),
        notes=[str(item) for item in list(summary.get("notes", []) or [])],
        current=ProviderCohortDTO(**dict(summary.get("current", {}) or {})),
        previous=ProviderCohortDTO(**previous) if previous else None,
        deltas={str(key): float(value) for key, value in dict(summary.get("deltas", {}) or {}).items()},
    )


def _to_research_batch_dto(record) -> ResearchBatchDTO:
    return ResearchBatchDTO(
        batch_id=record.batch_id,
        market_scope=record.market_scope,
        status=record.status,
        research_symbols=list(record.research_symbols),
        selected_challenger_symbol=record.selected_challenger_symbol,
        summary_payload=dict(record.summary_payload),
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _to_knowledge_source_dto(record) -> KnowledgeSourceDTO:
    return KnowledgeSourceDTO(
        source_id=record.source_id,
        source_name=record.source_name,
        source_kind=record.source_kind,
        publisher=record.publisher,
        url=record.url,
        license_note=record.license_note,
        trust_tier=record.trust_tier,
        enabled=record.enabled,
        last_reviewed_at=record.last_reviewed_at,
    )


def _to_knowledge_suggestion_dto(record) -> KnowledgeSuggestionDTO:
    return KnowledgeSuggestionDTO(
        suggestion_id=record.suggestion_id,
        family_key=record.family_key,
        market_scope=record.market_scope,
        origin=record.origin,
        suggestion_type=record.suggestion_type,
        current_value=dict(record.current_value),
        suggested_value=dict(record.suggested_value),
        rationale_zh=record.rationale_zh,
        confidence=record.confidence,
        evidence_counts=dict(record.evidence_counts),
        linked_source_ids=list(record.linked_source_ids),
        status=record.status,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _to_provider_migration_history_dto(items: list[dict[str, object]]) -> list[ProviderCohortHistoryItemDTO]:
    return [ProviderCohortHistoryItemDTO(**item) for item in items]


def _to_runtime_sync_history_dto(items: list[dict[str, object]]) -> list[RuntimeSyncHistoryItemDTO]:
    return [RuntimeSyncHistoryItemDTO(**item) for item in items]


def _read_runtime_log(stream: str, *, lines: int = 120) -> RuntimeLogDTO:
    if stream not in RUNTIME_LOG_PATHS:
        raise HTTPException(status_code=400, detail="Unsupported log stream")
    path = RUNTIME_LOG_PATHS[stream]
    max_lines = max(20, min(lines, 400))
    if not path.exists():
        return RuntimeLogDTO(stream=stream, path=str(path), exists=False, lines=[])
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            tail = list(deque((line.rstrip("\n") for line in handle), maxlen=max_lines))
        updated_at = datetime.fromtimestamp(path.stat().st_mtime)
        return RuntimeLogDTO(
            stream=stream, path=str(path), exists=True, updated_at=updated_at, lines=tail
        )
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read runtime log: {exc}") from exc


def _governance_block(report: dict[str, object] | None, key: str) -> dict[str, object]:
    if not isinstance(report, dict):
        return {}
    value = report.get(key, {})
    return dict(value) if isinstance(value, dict) else {}


def _paper_summary(paper_raw: dict[str, object], latest_execution: dict[str, object] | None) -> PaperSummaryDTO:
    nav_rows = list(paper_raw.get("nav", []) or [])
    positions = list(paper_raw.get("positions", []) or [])
    latest_equity = None
    latest_nav_change = None
    if nav_rows:
        latest_equity = float(nav_rows[0].get("total_equity", 0.0) or 0.0)
        if len(nav_rows) >= 2:
            previous_equity = float(nav_rows[1].get("total_equity", 0.0) or 0.0)
            latest_nav_change = round(latest_equity - previous_equity, 2)
    return PaperSummaryDTO(
        total_equity=latest_equity,
        position_count=len(positions),
        latest_execution_status=str(latest_execution.get("status")) if latest_execution else None,
        latest_execution_explanation=str(latest_execution.get("explanation")) if latest_execution else None,
        latest_nav_change=latest_nav_change,
    )


def _candidate_gate_snapshot(proposal: StrategyProposal | None, live_readiness: dict[str, object]) -> SlotGateDTO:
    if proposal is None:
        return SlotGateDTO(eligible=False, blocked_reasons=list(live_readiness.get("blockers", [])[:3]), summary=live_readiness.get("summary"))
    governance_report = dict((proposal.evidence_pack or {}).get("governance_report", {}) or {})
    candidate_gate = _governance_block(governance_report, "candidate_gate")
    if candidate_gate:
        return SlotGateDTO(
            eligible=bool(candidate_gate.get("eligible", False)),
            blocked_reasons=[str(item) for item in list(candidate_gate.get("blocked_reasons", []) or [])],
            summary="候选池准入",
        )
    quality_report = dict((proposal.evidence_pack or {}).get("quality_report", {}) or {})
    backtest_gate = dict(quality_report.get("backtest_gate", {}) or {})
    review = dict(backtest_gate.get("review", {}) or {})
    hard_fails = [str(item) for item in list(review.get("hard_gates_failed", []) or [])]
    eligible = bool(backtest_gate.get("available")) and not hard_fails and proposal.final_score >= 68.0
    blocked = [] if eligible else (hard_fails or ["below_keep_threshold"])
    return SlotGateDTO(eligible=eligible, blocked_reasons=blocked, summary="候选池准入")


def _promotion_gate_snapshot(proposal: StrategyProposal | None, live_readiness: dict[str, object]) -> SlotGateDTO:
    if proposal is None:
        return SlotGateDTO(eligible=False, blocked_reasons=list(live_readiness.get("blockers", [])[:3]), summary=live_readiness.get("summary"))
    governance_report = dict((proposal.evidence_pack or {}).get("governance_report", {}) or {})
    promotion_gate = _governance_block(governance_report, "promotion_gate")
    if promotion_gate:
        return SlotGateDTO(
            eligible=bool(promotion_gate.get("eligible", False)),
            blocked_reasons=[str(item) for item in list(promotion_gate.get("blocked_reasons", []) or [])],
            summary=str(promotion_gate.get("backtest_summary") or "模拟盘准入"),
        )
    return SlotGateDTO(eligible=False, blocked_reasons=[], summary="模拟盘准入")


def _resolve_slot_focus(
    db: Session,
    *,
    active: StrategyProposal | None,
    runtime_status: dict[str, object],
    live_readiness: dict[str, object],
) -> SlotFocusDTO:
    focus_proposal = active
    mode = "active" if active is not None else "empty"
    if focus_proposal is None:
        candidates = [
            item
            for item in list_candidate_strategies(db)
            if item.status.value == "candidate" and item.source_kind != "mock"
        ]
        if candidates:
            focus_proposal = candidates[0]
            mode = "challenger"
        else:
            batches = list_research_batches(db, limit=4)
            batch_candidates: list[StrategyProposal] = []
            for batch in batches:
                batch_symbols = [str(item) for item in list(batch.research_symbols or []) if str(item).strip()]
                if not batch_symbols:
                    continue
                records = list(
                    db.execute(
                        select(StrategyProposal.id)
                        .where(
                            StrategyProposal.symbol.in_(batch_symbols),
                            StrategyProposal.created_at >= batch.created_at,
                        )
                        .order_by(StrategyProposal.final_score.desc(), StrategyProposal.created_at.desc())
                        .limit(6)
                    ).scalars()
                )
                for proposal_id in records:
                    proposal = get_strategy_proposal(db, proposal_id)
                    if proposal is not None and proposal.source_kind != "mock":
                        batch_candidates.append(proposal)
                if batch_candidates:
                    break
            if batch_candidates:
                batch_candidates.sort(
                    key=lambda item: (
                        bool(_candidate_gate_snapshot(item, live_readiness).eligible),
                        item.final_score,
                        item.created_at,
                    ),
                    reverse=True,
                )
                focus_proposal = batch_candidates[0]
                mode = "challenger"

    candidate_gate = _candidate_gate_snapshot(focus_proposal, live_readiness)
    promotion_gate = _promotion_gate_snapshot(focus_proposal, live_readiness)
    lifecycle = dict(((focus_proposal.evidence_pack or {}).get("governance_report", {}) or {}).get("lifecycle", {}) or {}) if focus_proposal else {}
    primary_blocker = None
    if candidate_gate.blocked_reasons:
        primary_blocker = candidate_gate.blocked_reasons[0]
    elif promotion_gate.blocked_reasons:
        primary_blocker = promotion_gate.blocked_reasons[0]
    elif live_readiness.get("blockers"):
        primary_blocker = str(list(live_readiness.get("blockers", []) or [])[0])
    next_step = None
    if lifecycle.get("next_step") is not None:
        next_step = str(lifecycle.get("next_step"))
    elif live_readiness.get("next_actions"):
        next_step = str(list(live_readiness.get("next_actions", []) or [])[0])
    elif runtime_status.get("current_stage") is not None:
        next_step = str(runtime_status.get("current_stage"))
    return SlotFocusDTO(
        mode=mode,
        strategy_title=focus_proposal.title if focus_proposal else None,
        symbol=focus_proposal.symbol if focus_proposal else None,
        proposal_id=focus_proposal.id if focus_proposal else None,
        stage=str(runtime_status.get("current_stage")) if runtime_status.get("current_stage") is not None else None,
        candidate_gate=candidate_gate,
        promotion_gate=promotion_gate,
        live_readiness_summary=str(live_readiness.get("summary", "")) if live_readiness else None,
        primary_blocker=primary_blocker,
        next_step=next_step,
    )


@router.get("/command", response_model=CommandCenterDTO)
def get_command_center(db: Session = Depends(get_db)) -> CommandCenterDTO:
    active = get_active_strategy(db)
    latest_decision = get_latest_risk_decision(db)
    snapshot = build_market_snapshot(db)
    runtime_status = get_pipeline_runtime_status(db)
    paper_raw = fetch_paper_data(limit=30)
    latest_execution_payload = get_latest_paper_execution(db, active)
    paper_dto = PaperTradingDTO(
        nav=[PaperNavPointDTO(**item) for item in paper_raw["nav"]],
        orders=[PaperOrderDTO(**item) for item in paper_raw["orders"]],
        positions=[PaperPositionDTO(**item) for item in paper_raw["positions"]],
        latest_execution=PaperExecutionDTO(**latest_execution_payload) if latest_execution_payload else None,
    )
    latest_digest = snapshot["event_digest"]
    provider_migration = build_provider_migration_summary(db)
    runtime_sync_history = build_runtime_sync_history(db)
    provider_migration_history = build_provider_migration_history(db)
    live_readiness = build_live_readiness(db)
    live_readiness_history = build_live_readiness_history(db, limit=8)
    live_readiness_change = build_live_readiness_change(db, live_readiness_history)
    slot_focus = _resolve_slot_focus(db, active=active, runtime_status=runtime_status, live_readiness=live_readiness)
    paper_summary = _paper_summary(paper_raw, latest_execution_payload)
    return CommandCenterDTO(
        generated_at=now_tz(),
        timezone="Asia/Shanghai",
        llm_status=_to_llm_status_dto(get_current_llm_status(db)),
        runtime_status=_to_pipeline_runtime_status_dto(runtime_status),
        runtime_sync_history=_to_runtime_sync_history_dto(runtime_sync_history),
        provider_migration=_to_provider_migration_summary_dto(provider_migration),
        provider_migration_history=_to_provider_migration_history_dto(provider_migration_history),
        live_readiness=LiveReadinessDTO(**live_readiness),
        live_readiness_history=[LiveReadinessHistoryItemDTO(**item) for item in live_readiness_history],
        live_readiness_change=LiveReadinessChangeDTO(**live_readiness_change) if live_readiness_change else None,
        market_snapshot=MarketSnapshotDTO(
            regime=str(snapshot["regime"]),
            confidence=float(snapshot["confidence"]),
            summary=str(snapshot["summary"]),
            market_snapshot_hash=str(snapshot["market_snapshot_hash"]),
            symbol=str(snapshot["symbol"]),
            price_context=dict(snapshot["price_context"]),
            event_lane_sources={str(key): str(value) for key, value in dict(snapshot["event_lane_sources"]).items()},
            market_profile=MarketProfileDTO(**dict(snapshot["market_profile"])),
            universe_selection=UniverseSelectionDTO(
                mode=str(dict(snapshot["universe_selection"]).get("mode", "static_hk")),
                market_scope=str(dict(snapshot["universe_selection"]).get("market_scope", "HK")),
                selected_symbol=str(dict(snapshot["universe_selection"]).get("selected_symbol", snapshot["symbol"])),
                source=str(dict(snapshot["universe_selection"]).get("source", "static")),
                generated_at=dict(snapshot["universe_selection"]).get("generated_at"),
                selection_reason=dict(snapshot["universe_selection"]).get("selection_reason"),
                top_factors=[str(item) for item in list(dict(snapshot["universe_selection"]).get("top_factors", []))],
                candidate_count=int(dict(snapshot["universe_selection"]).get("candidate_count", 0) or 0),
                top_n_limit=dict(snapshot["universe_selection"]).get("top_n_limit"),
                min_turnover_millions=dict(snapshot["universe_selection"]).get("min_turnover_millions"),
                account_capital_hkd=dict(snapshot["universe_selection"]).get("account_capital_hkd"),
                max_lot_cost_ratio=dict(snapshot["universe_selection"]).get("max_lot_cost_ratio"),
                benchmark_symbol=dict(snapshot["universe_selection"]).get("benchmark_symbol"),
                benchmark_gap=dict(snapshot["universe_selection"]).get("benchmark_gap"),
                benchmark_candidate=UniverseCandidateDTO(**dict(snapshot["universe_selection"]).get("benchmark_candidate"))
                if dict(snapshot["universe_selection"]).get("benchmark_candidate")
                else None,
                research_symbols=[
                    str(item)
                    for item in list(dict(snapshot["universe_selection"]).get("research_symbols", []))
                ],
                candidates=[
                    UniverseCandidateDTO(**candidate)
                    for candidate in list(dict(snapshot["universe_selection"]).get("candidates", []))
                ],
            ),
            macro_status=MacroPipelineStatusDTO(**dict(snapshot["macro_status"])),
            event_digest=_to_digest_dto(snapshot["event_digest"]),
            event_stream_preview=[_to_event_dto(record) for record in snapshot["event_stream_preview"]],
        ),
        slot_focus=slot_focus,
        paper_summary=paper_summary,
        active_strategy=ActiveStrategyDTO(
            proposal=_to_proposal_dto(active) if active else None,
            latest_decision=_to_risk_decision_dto(active.decisions[-1]) if active and active.decisions else None,
            paper_trading=paper_dto,
            operational_acceptance=build_operational_acceptance(
                proposal=active,
                latest_decision=active.decisions[-1] if active and active.decisions else None,
                nav_rows=paper_raw["nav"],
                orders=paper_raw["orders"],
                macro_status=dict(snapshot["macro_status"]),
                market_scope=str(snapshot["event_digest"].market_scope),
                current_time=now_tz(),
            ) if active else {},
        ),
        candidate_count=len(list_candidate_strategies(db)),
        latest_risk_decision=_to_risk_decision_dto(latest_decision) if latest_decision else None,
        latest_audit_events=[_to_audit_dto(item) for item in list_audit_records(db, limit=8)],
        latest_event_digest=_to_digest_dto(latest_digest),
    )


@router.get("/ops/acceptance-report", response_model=AcceptanceReportDTO)
def get_acceptance_report(
    window_days: int = Query(default=30, ge=7, le=180),
    db: Session = Depends(get_db),
) -> AcceptanceReportDTO:
    return AcceptanceReportDTO(**build_acceptance_report(db, window_days=window_days))


@router.get("/runtime/llm", response_model=LLMStatusDTO)
def get_runtime_llm(db: Session = Depends(get_db)) -> LLMStatusDTO:
    return _to_llm_status_dto(get_current_llm_status(db))


@router.patch("/runtime/llm", response_model=LLMStatusDTO)
def patch_runtime_llm(
    payload: RuntimeLLMUpdate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> LLMStatusDTO:
    status, changed = set_runtime_llm_provider(db, payload.provider)
    if not changed:
        raise HTTPException(status_code=400, detail=status.message)
    runtime_status = get_pipeline_runtime_status(db)
    if runtime_status.get('current_state') != 'running':
        background_tasks.add_task(_run_runtime_provider_switch_sync_job)
    return _to_llm_status_dto(status)


@router.post("/runtime/sync", response_model=PipelineRuntimeStatusDTO)
def trigger_runtime_sync(background_tasks: BackgroundTasks, db: Session = Depends(get_db)) -> PipelineRuntimeStatusDTO:
    status = get_pipeline_runtime_status(db)
    if str(status.get('current_state')) == 'running':
        raise HTTPException(status_code=409, detail="Pipeline sync is already running")
    background_tasks.add_task(_run_manual_sync_job)
    return _to_pipeline_runtime_status_dto(status)


@router.get("/runtime/logs", response_model=RuntimeLogDTO)
def get_runtime_logs(
    stream: str = Query(default="out", pattern="^(out|err)$"),
    lines: int = Query(default=120, ge=20, le=400),
) -> RuntimeLogDTO:
    return _read_runtime_log(stream, lines=lines)


@router.get("/candidates", response_model=list[CandidateStrategyDTO])
def get_candidates(db: Session = Depends(get_db)) -> list[CandidateStrategyDTO]:
    records = list_candidate_strategies(db)
    return [
        CandidateStrategyDTO(
            proposal=_to_proposal_dto(record),
            latest_decision=_to_risk_decision_dto(record.decisions[-1]) if record.decisions else None,
        )
        for record in records
    ]


@router.get("/candidates/{proposal_id}", response_model=CandidateStrategyDTO)
def get_candidate(proposal_id: str, db: Session = Depends(get_db)) -> CandidateStrategyDTO:
    proposal = get_strategy_proposal(db, proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail="Candidate strategy not found")
    return CandidateStrategyDTO(
        proposal=_to_proposal_dto(proposal),
        latest_decision=_to_risk_decision_dto(proposal.decisions[-1]) if proposal.decisions else None,
    )


@router.get("/research/proposals", response_model=list[StrategyProposalDTO])
def get_research_proposals(db: Session = Depends(get_db)) -> list[StrategyProposalDTO]:
    return [_to_proposal_dto(record) for record in list_strategy_proposals(db)]


@router.get("/research/proposals/{proposal_id}", response_model=StrategyProposalDTO)
def get_research_proposal(proposal_id: str, db: Session = Depends(get_db)) -> StrategyProposalDTO:
    proposal = get_strategy_proposal(db, proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail="Strategy proposal not found")
    return _to_proposal_dto(proposal)


@router.get("/research/batches", response_model=list[ResearchBatchDTO])
def get_research_batches(limit: int = Query(default=20, ge=1, le=100), db: Session = Depends(get_db)) -> list[ResearchBatchDTO]:
    return [_to_research_batch_dto(record) for record in list_research_batches(db, limit=limit)]


@router.get("/research/batches/{batch_id}", response_model=ResearchBatchDTO)
def get_research_batch_detail(batch_id: str, db: Session = Depends(get_db)) -> ResearchBatchDTO:
    record = get_research_batch(db, batch_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Research batch not found")
    return _to_research_batch_dto(record)


@router.get("/paper/active-strategy", response_model=ActiveStrategyDTO)
def get_paper_active_strategy(db: Session = Depends(get_db)) -> ActiveStrategyDTO:
    active = get_active_strategy(db)
    paper_raw = fetch_paper_data(limit=120)
    snapshot = build_market_snapshot(db)
    return ActiveStrategyDTO(
        proposal=_to_proposal_dto(active) if active else None,
        latest_decision=_to_risk_decision_dto(active.decisions[-1]) if active and active.decisions else None,
        paper_trading=PaperTradingDTO(
            nav=[PaperNavPointDTO(**item) for item in paper_raw["nav"]],
            orders=[PaperOrderDTO(**item) for item in paper_raw["orders"]],
            positions=[PaperPositionDTO(**item) for item in paper_raw["positions"]],
            latest_execution=PaperExecutionDTO(**latest_execution) if (latest_execution := get_latest_paper_execution(db, active)) else None,
        ),
        operational_acceptance=build_operational_acceptance(
            proposal=active,
            latest_decision=active.decisions[-1] if active and active.decisions else None,
            nav_rows=paper_raw["nav"],
            orders=paper_raw["orders"],
            macro_status=dict(snapshot["macro_status"]),
            market_scope=str(snapshot["event_digest"].market_scope),
            current_time=now_tz(),
        ) if active else {},
    )


@router.get("/risk/decisions", response_model=list[RiskDecisionDTO])
def get_risk_decisions(limit: int = Query(default=50, ge=1, le=200), db: Session = Depends(get_db)) -> list[RiskDecisionDTO]:
    return [_to_risk_decision_dto(record) for record in list_risk_decisions(db, limit=limit)]


@router.get("/audit/events", response_model=list[AuditRecordDTO])
def get_audit_events(limit: int = Query(default=100, ge=1, le=500), db: Session = Depends(get_db)) -> list[AuditRecordDTO]:
    return [_to_audit_dto(record) for record in list_audit_records(db, limit=limit)]


@router.get("/knowledge/sources", response_model=list[KnowledgeSourceDTO])
def get_knowledge_sources(db: Session = Depends(get_db)) -> list[KnowledgeSourceDTO]:
    return [_to_knowledge_source_dto(record) for record in list_knowledge_sources(db)]


@router.get("/knowledge/suggestions", response_model=list[KnowledgeSuggestionDTO])
def get_knowledge_suggestions(limit: int = Query(default=100, ge=1, le=200), db: Session = Depends(get_db)) -> list[KnowledgeSuggestionDTO]:
    return [_to_knowledge_suggestion_dto(record) for record in list_knowledge_suggestions(db, limit=limit)]


@router.get("/knowledge/suggestions/{suggestion_id}", response_model=KnowledgeSuggestionDTO)
def get_knowledge_suggestion_detail(suggestion_id: str, db: Session = Depends(get_db)) -> KnowledgeSuggestionDTO:
    record = get_knowledge_suggestion(db, suggestion_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Knowledge suggestion not found")
    return _to_knowledge_suggestion_dto(record)


@router.get("/events/daily-digests", response_model=list[DailyEventDigestDTO])
def get_daily_event_digests(limit: int = Query(default=30, ge=1, le=120), db: Session = Depends(get_db)) -> list[DailyEventDigestDTO]:
    return [_to_digest_dto(record) for record in list_event_digests(db, limit=limit)]


@router.get("/events/stream", response_model=list[EventRecordDTO])
def get_event_stream(limit: int = Query(default=100, ge=1, le=500), db: Session = Depends(get_db)) -> list[EventRecordDTO]:
    return [_to_event_dto(record) for record in list_event_stream(db, limit=limit)]


@router.get("/strategies", response_model=list[StrategySnapshotDTO])
def list_strategies(db: Session = Depends(get_db)) -> list[StrategySnapshotDTO]:
    records = list(db.query(StrategySnapshot).order_by(StrategySnapshot.strategy_name.asc()).all())
    return [
        StrategySnapshotDTO(
            strategy_name=record.strategy_name,
            description=record.description,
            enabled=record.enabled,
            default_params=record.default_params,
            tags=list(get_strategy_registry().get(record.strategy_name).tags),
            supported_markets=list(get_strategy_registry().get(record.strategy_name).supported_markets),
            market_bias=get_strategy_registry().get(record.strategy_name).market_bias,
            knowledge_families=list(get_strategy_registry().get(record.strategy_name).knowledge_families),
            strategy_family_label_zh=get_strategy_registry().get(record.strategy_name).strategy_family_label_zh,
            knowledge_notes_zh=get_strategy_registry().get(record.strategy_name).knowledge_notes_zh,
            updated_at=record.updated_at,
        )
        for record in records
    ]


@router.post("/backtests/runs", response_model=CreatedRunResponse)
def create_backtest_run(payload: BacktestRunCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)) -> CreatedRunResponse:
    now = now_tz()
    run = BacktestRun(
        symbol=payload.symbol,
        strategy_name=payload.strategy_name,
        provider_name=payload.provider_name,
        status=RunStatus.QUEUED,
        request_payload=payload.model_dump(),
        created_at=now,
        updated_at=now,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    background_tasks.add_task(execute_backtest_run, run.id)
    return CreatedRunResponse(run_id=run.id, status="queued")


@router.get("/backtests/runs", response_model=list[BacktestRunDTO])
def list_backtest_runs(limit: int = Query(default=100, ge=1, le=500), db: Session = Depends(get_db)) -> list[BacktestRunDTO]:
    return [_to_backtest_dto(record) for record in list_backtest_runs_with_metrics(db, limit=limit)]


@router.get("/backtests/runs/{run_id}", response_model=BacktestRunDTO)
def get_backtest_run(run_id: str, db: Session = Depends(get_db)) -> BacktestRunDTO:
    run = get_backtest_run_with_metrics(db, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Backtest run not found")
    return _to_backtest_dto(run)


@router.post("/experiments/optimizer-runs", response_model=CreatedRunResponse)
def create_optimizer_run(payload: ExperimentRunCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)) -> CreatedRunResponse:
    now = now_tz()
    run = ExperimentRun(
        kind="optimizer",
        symbol=payload.symbol,
        strategy_name=payload.strategy_name,
        provider_name=payload.provider_name,
        status=RunStatus.QUEUED,
        request_payload=payload.model_dump(),
        created_at=now,
        updated_at=now,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    background_tasks.add_task(execute_experiment_run, run.id)
    return CreatedRunResponse(run_id=run.id, status="queued")


@router.post("/experiments/walkforward-runs", response_model=CreatedRunResponse)
def create_walkforward_run(payload: ExperimentRunCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)) -> CreatedRunResponse:
    now = now_tz()
    run = ExperimentRun(
        kind="walkforward",
        symbol=payload.symbol,
        strategy_name=payload.strategy_name,
        provider_name=payload.provider_name,
        status=RunStatus.QUEUED,
        request_payload=payload.model_dump(),
        created_at=now,
        updated_at=now,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    background_tasks.add_task(execute_experiment_run, run.id)
    return CreatedRunResponse(run_id=run.id, status="queued")


@router.get("/experiments/runs", response_model=list[ExperimentRunDTO])
def list_experiment_runs(limit: int = Query(default=100, ge=1, le=500), db: Session = Depends(get_db)) -> list[ExperimentRunDTO]:
    return [_to_experiment_dto(record) for record in list_experiment_runs_with_metrics(db, limit=limit)]


@router.get("/experiments/runs/{run_id}", response_model=ExperimentRunDTO)
def get_experiment_run(run_id: str, db: Session = Depends(get_db)) -> ExperimentRunDTO:
    run = get_experiment_run_with_metrics(db, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Experiment run not found")
    return _to_experiment_dto(run)


@router.get("/paper/nav", response_model=list[PaperNavPointDTO])
def get_paper_nav(limit: int = Query(default=180, ge=1, le=2000)) -> list[PaperNavPointDTO]:
    return _to_paper_dto(limit=limit).nav


@router.get("/paper/orders", response_model=list[PaperOrderDTO])
def get_paper_orders(limit: int = Query(default=200, ge=1, le=1000)) -> list[PaperOrderDTO]:
    return _to_paper_dto(limit=limit).orders


@router.get("/paper/positions", response_model=list[PaperPositionDTO])
def get_paper_positions(limit: int = Query(default=200, ge=1, le=1000)) -> list[PaperPositionDTO]:
    return _to_paper_dto(limit=limit).positions


@asynccontextmanager
async def lifespan(_: FastAPI):
    global PROCESS_STARTED_AT
    init_database()
    PROCESS_STARTED_AT = now_tz()
    scheduler = build_pipeline_scheduler()
    with SessionLocal() as db:
        sync_strategy_snapshots(db)
    scheduler.start()
    startup_task = asyncio.create_task(asyncio.to_thread(_run_startup_sync_job))
    try:
        yield
    finally:
        startup_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await startup_task
        await scheduler.stop()


def create_app() -> FastAPI:
    app = FastAPI(title="GobyShrimp API", version="1.3.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[],
        allow_origin_regex=r"http://(127\.0\.0\.1|localhost):\d+",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    if FRONTEND_DIST_DIR.exists():
        assets_dir = FRONTEND_DIST_DIR / "assets"
        if assets_dir.exists():
            app.mount("/assets", StaticFiles(directory=assets_dir), name="frontend-assets")

        @app.get("/", include_in_schema=False)
        def frontend_index() -> FileResponse:
            return FileResponse(FRONTEND_DIST_DIR / "index.html")

        @app.get("/{full_path:path}", include_in_schema=False)
        def frontend_spa(full_path: str) -> FileResponse:
            candidate = FRONTEND_DIST_DIR / full_path
            if candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(FRONTEND_DIST_DIR / "index.html")

    return app


app = create_app()
