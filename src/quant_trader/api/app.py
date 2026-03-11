from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from .db import SessionLocal, get_db, init_database
from .models import (
    BacktestRun,
    ExperimentKind,
    ExperimentRun,
    RunStatus,
    StrategySnapshot,
)
from .schemas import (
    BacktestRunCreate,
    BacktestRunDTO,
    CreatedRunResponse,
    ExperimentRunCreate,
    ExperimentRunDTO,
    OverviewDTO,
    PaperNavPointDTO,
    PaperOrderDTO,
    PaperPositionDTO,
    PaperTradingDTO,
    RunMetricSnapshotDTO,
    StrategySnapshotDTO,
)
from .services import (
    execute_backtest_run,
    execute_experiment_run,
    get_backtest_run_with_metrics,
    get_experiment_run_with_metrics,
    get_running_jobs_count,
    list_backtest_runs_with_metrics,
    list_experiment_runs_with_metrics,
    now_tz,
    sync_strategy_snapshots,
)

router = APIRouter(prefix="/api/v1")


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


def _read_sqlite_rows(db_path: str, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    path = Path(db_path)
    if not path.exists():
        return []
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.OperationalError:
        rows = []
    finally:
        conn.close()
    return rows


def _fetch_paper_data(limit: int = 100) -> PaperTradingDTO:
    settings = get_settings()
    db_paths = [settings.storage.runtime_db_path, settings.storage.paper_db_path]

    nav_rows: list[sqlite3.Row] = []
    order_rows: list[sqlite3.Row] = []
    position_rows: list[sqlite3.Row] = []

    for db_path in db_paths:
        if not nav_rows:
            nav_rows = _read_sqlite_rows(
                db_path,
                "SELECT trade_date, cash, position_value, total_equity FROM daily_nav ORDER BY trade_date DESC LIMIT ?",
                (limit,),
            )
        if not order_rows:
            order_rows = _read_sqlite_rows(
                db_path,
                "SELECT id, symbol, side, quantity, price, amount, status, created_at FROM orders ORDER BY created_at DESC LIMIT ?",
                (limit,),
            )
        if not position_rows:
            position_rows = _read_sqlite_rows(
                db_path,
                "SELECT id, symbol, quantity, avg_cost, market_value, updated_at FROM positions ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            )

    return PaperTradingDTO(
        nav=[
            PaperNavPointDTO(
                trade_date=row["trade_date"],
                cash=float(row["cash"]),
                position_value=float(row["position_value"]),
                total_equity=float(row["total_equity"]),
            )
            for row in nav_rows
        ],
        orders=[
            PaperOrderDTO(
                id=int(row["id"]),
                symbol=row["symbol"],
                side=row["side"],
                quantity=int(row["quantity"]),
                price=float(row["price"]),
                amount=float(row["amount"]),
                status=row["status"],
                created_at=row["created_at"],
            )
            for row in order_rows
        ],
        positions=[
            PaperPositionDTO(
                id=int(row["id"]),
                symbol=row["symbol"],
                quantity=int(row["quantity"]),
                avg_cost=float(row["avg_cost"]),
                market_value=float(row["market_value"]),
                updated_at=row["updated_at"],
            )
            for row in position_rows
        ],
    )


@router.get("/overview", response_model=OverviewDTO)
def get_overview(db: Session = Depends(get_db)) -> OverviewDTO:
    latest_backtest = None
    latest_experiment = None

    latest_backtest_id = db.execute(
        select(BacktestRun.id).order_by(BacktestRun.created_at.desc()).limit(1)
    ).scalar_one_or_none()
    if latest_backtest_id is not None:
        latest_backtest_record = get_backtest_run_with_metrics(db, latest_backtest_id)
        if latest_backtest_record is not None:
            latest_backtest = _to_backtest_dto(latest_backtest_record)

    latest_experiment_id = db.execute(
        select(ExperimentRun.id).order_by(ExperimentRun.created_at.desc()).limit(1)
    ).scalar_one_or_none()
    if latest_experiment_id is not None:
        latest_experiment_record = get_experiment_run_with_metrics(db, latest_experiment_id)
        if latest_experiment_record is not None:
            latest_experiment = _to_experiment_dto(latest_experiment_record)

    paper_data = _fetch_paper_data(limit=1)
    latest_equity = paper_data.nav[0].total_equity if paper_data.nav else None
    latest_trade_date = paper_data.nav[0].trade_date if paper_data.nav else None

    return OverviewDTO(
        generated_at=now_tz(),
        timezone=get_settings().timezone,
        total_backtest_runs=int(db.execute(select(func.count()).select_from(BacktestRun)).scalar_one()),
        total_experiment_runs=int(db.execute(select(func.count()).select_from(ExperimentRun)).scalar_one()),
        running_jobs=get_running_jobs_count(db),
        latest_backtest=latest_backtest,
        latest_experiment=latest_experiment,
        latest_total_equity=latest_equity,
        latest_trade_date=latest_trade_date,
    )


@router.get("/strategies", response_model=list[StrategySnapshotDTO])
def list_strategies(db: Session = Depends(get_db)) -> list[StrategySnapshotDTO]:
    records = list(db.execute(select(StrategySnapshot).order_by(StrategySnapshot.strategy_name.asc())).scalars())
    return [
        StrategySnapshotDTO(
            strategy_name=record.strategy_name,
            description=record.description,
            enabled=record.enabled,
            default_params=record.default_params,
            updated_at=record.updated_at,
        )
        for record in records
    ]


@router.post("/backtests/runs", response_model=CreatedRunResponse)
def create_backtest_run(
    payload: BacktestRunCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> CreatedRunResponse:
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
def list_backtest_runs(
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[BacktestRunDTO]:
    return [_to_backtest_dto(record) for record in list_backtest_runs_with_metrics(db, limit=limit)]


@router.get("/backtests/runs/{run_id}", response_model=BacktestRunDTO)
def get_backtest_run(run_id: str, db: Session = Depends(get_db)) -> BacktestRunDTO:
    run = get_backtest_run_with_metrics(db, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Backtest run not found")
    return _to_backtest_dto(run)


@router.post("/experiments/optimizer-runs", response_model=CreatedRunResponse)
def create_optimizer_run(
    payload: ExperimentRunCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> CreatedRunResponse:
    now = now_tz()
    run = ExperimentRun(
        kind=ExperimentKind.OPTIMIZER,
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
def create_walkforward_run(
    payload: ExperimentRunCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> CreatedRunResponse:
    now = now_tz()
    run = ExperimentRun(
        kind=ExperimentKind.WALKFORWARD,
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
def list_experiment_runs(
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[ExperimentRunDTO]:
    return [_to_experiment_dto(record) for record in list_experiment_runs_with_metrics(db, limit=limit)]


@router.get("/experiments/runs/{run_id}", response_model=ExperimentRunDTO)
def get_experiment_run(run_id: str, db: Session = Depends(get_db)) -> ExperimentRunDTO:
    run = get_experiment_run_with_metrics(db, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Experiment run not found")
    return _to_experiment_dto(run)


@router.get("/paper/nav", response_model=list[PaperNavPointDTO])
def get_paper_nav(limit: int = Query(default=180, ge=1, le=2000)) -> list[PaperNavPointDTO]:
    return _fetch_paper_data(limit=limit).nav


@router.get("/paper/orders", response_model=list[PaperOrderDTO])
def get_paper_orders(limit: int = Query(default=200, ge=1, le=1000)) -> list[PaperOrderDTO]:
    return _fetch_paper_data(limit=limit).orders


@router.get("/paper/positions", response_model=list[PaperPositionDTO])
def get_paper_positions(limit: int = Query(default=200, ge=1, le=1000)) -> list[PaperPositionDTO]:
    return _fetch_paper_data(limit=limit).positions


def create_app() -> FastAPI:
    app = FastAPI(title="quant-trader API", version="1.0.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.on_event("startup")
    def startup() -> None:
        init_database()
        with SessionLocal() as db:
            sync_strategy_snapshots(db)

    return app


app = create_app()
