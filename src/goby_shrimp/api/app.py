from __future__ import annotations

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from fastapi import APIRouter, BackgroundTasks, Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
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
    RiskDecisionDTO,
    RuntimeLLMUpdate,
    RunMetricSnapshotDTO,
    StrategyProposalDTO,
    StrategySnapshotDTO,
)
from .services import (
    build_acceptance_report,
    build_operational_acceptance,
    build_market_snapshot,
    execute_backtest_run,
    execute_experiment_run,
    fetch_paper_data,
    get_active_strategy,
    get_backtest_run_with_metrics,
    get_current_llm_status,
    get_latest_paper_execution,
    get_pipeline_runtime_status,
    get_experiment_run_with_metrics,
    get_latest_risk_decision,
    get_strategy_proposal,
    list_audit_records,
    list_backtest_runs_with_metrics,
    list_candidate_strategies,
    list_event_digests,
    list_event_stream,
    list_experiment_runs_with_metrics,
    list_risk_decisions,
    list_strategy_proposals,
    now_tz,
    set_runtime_llm_provider,
    sync_agent_state,
    sync_strategy_snapshots,
)

router = APIRouter(prefix="/api/v1")
logger = logging.getLogger(__name__)


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
    )


@router.get("/command", response_model=CommandCenterDTO)
def get_command_center(db: Session = Depends(get_db)) -> CommandCenterDTO:
    active = get_active_strategy(db)
    latest_decision = get_latest_risk_decision(db)
    snapshot = build_market_snapshot(db)
    paper_raw = fetch_paper_data(limit=30)
    paper_dto = PaperTradingDTO(
        nav=[PaperNavPointDTO(**item) for item in paper_raw["nav"]],
        orders=[PaperOrderDTO(**item) for item in paper_raw["orders"]],
        positions=[PaperPositionDTO(**item) for item in paper_raw["positions"]],
        latest_execution=PaperExecutionDTO(**latest_execution) if (latest_execution := get_latest_paper_execution(db, active)) else None,
    )
    latest_digest = snapshot["event_digest"]
    return CommandCenterDTO(
        generated_at=now_tz(),
        timezone="Asia/Shanghai",
        llm_status=_to_llm_status_dto(get_current_llm_status(db)),
        runtime_status=_to_pipeline_runtime_status_dto(get_pipeline_runtime_status(db)),
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
                benchmark_symbol=dict(snapshot["universe_selection"]).get("benchmark_symbol"),
                benchmark_gap=dict(snapshot["universe_selection"]).get("benchmark_gap"),
                benchmark_candidate=UniverseCandidateDTO(**dict(snapshot["universe_selection"]).get("benchmark_candidate"))
                if dict(snapshot["universe_selection"]).get("benchmark_candidate")
                else None,
                candidates=[
                    UniverseCandidateDTO(**candidate)
                    for candidate in list(dict(snapshot["universe_selection"]).get("candidates", []))
                ],
            ),
            macro_status=MacroPipelineStatusDTO(**dict(snapshot["macro_status"])),
            event_digest=_to_digest_dto(snapshot["event_digest"]),
            event_stream_preview=[_to_event_dto(record) for record in snapshot["event_stream_preview"]],
        ),
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


@router.get("/research/proposals", response_model=list[StrategyProposalDTO])
def get_research_proposals(db: Session = Depends(get_db)) -> list[StrategyProposalDTO]:
    return [_to_proposal_dto(record) for record in list_strategy_proposals(db)]


@router.get("/research/proposals/{proposal_id}", response_model=StrategyProposalDTO)
def get_research_proposal(proposal_id: str, db: Session = Depends(get_db)) -> StrategyProposalDTO:
    proposal = get_strategy_proposal(db, proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail="Strategy proposal not found")
    return _to_proposal_dto(proposal)


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
    init_database()
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

    return app


app = create_app()
