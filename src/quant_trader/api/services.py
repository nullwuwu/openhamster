from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..backtest.backtest_engine import BacktestEngine
from ..backtest.optimizer import MultiStrategyOptimizer
from ..backtest.walk_forward import WalkForwardEngine
from ..config import get_settings
from ..data import get_provider
from ..strategy import get_strategy_factory
from .db import SessionLocal
from .models import (
    BacktestRun,
    ExperimentKind,
    ExperimentRun,
    RunMetricSnapshot,
    RunStatus,
    StrategySnapshot,
)


def now_tz() -> datetime:
    settings = get_settings()
    return datetime.now(ZoneInfo(settings.timezone))


def sync_strategy_snapshots(db: Session) -> None:
    settings = get_settings()
    factory = get_strategy_factory()
    known = set(factory.registry.names())
    enabled = set(settings.strategy.enabled)

    for strategy_name in sorted(known):
        description = f"Built-in strategy: {strategy_name}"
        default_params = {}
        try:
            definition = factory.registry.get(strategy_name)
            default_params = definition.default_params
        except Exception:
            pass

        record = db.execute(
            select(StrategySnapshot).where(StrategySnapshot.strategy_name == strategy_name)
        ).scalar_one_or_none()

        if record is None:
            db.add(
                StrategySnapshot(
                    strategy_name=strategy_name,
                    description=description,
                    default_params=default_params,
                    enabled=strategy_name in enabled,
                    updated_at=now_tz(),
                )
            )
        else:
            record.description = description
            record.default_params = default_params
            record.enabled = strategy_name in enabled
            record.updated_at = now_tz()

    db.commit()


def execute_backtest_run(run_id: str) -> None:
    with SessionLocal() as db:
        run = db.execute(select(BacktestRun).where(BacktestRun.id == run_id)).scalar_one_or_none()
        if run is None:
            return

        run.status = RunStatus.RUNNING
        run.started_at = now_tz()
        run.updated_at = run.started_at
        db.commit()

        try:
            payload = dict(run.request_payload)
            strategy_factory = get_strategy_factory()
            strategy = strategy_factory.create(
                name=payload["strategy_name"],
                mode="vectorized",
                params=payload.get("strategy_params", {}),
            )

            provider_name = payload.get("provider_name")
            provider = get_provider(provider_name) if provider_name else None
            engine = BacktestEngine(data_provider=provider)
            result = engine.run(
                ticker=payload["symbol"],
                strategy=strategy,
                start_date=payload.get("start_date", "2020-01-01"),
                end_date=payload.get("end_date"),
                initial_capital=float(payload.get("initial_capital", 100000)),
                is_first_live=bool(payload.get("is_first_live", False)),
            )

            run.response_payload = result.model_dump()
            run.status = RunStatus.SUCCEEDED
            run.finished_at = now_tz()
            run.updated_at = run.finished_at

            db.add(
                RunMetricSnapshot(
                    run_type="backtest",
                    run_id=run.id,
                    backtest_run_id=run.id,
                    cagr=result.cagr,
                    max_drawdown=result.max_drawdown,
                    sharpe=result.sharpe,
                    annual_turnover=result.annual_turnover,
                    data_years=result.data_years,
                    metadata_payload={
                        "assumptions": result.assumptions,
                        "param_sensitivity": result.param_sensitivity,
                    },
                    created_at=now_tz(),
                )
            )
            db.commit()
        except Exception as exc:
            run.status = RunStatus.FAILED
            run.error_message = str(exc)
            run.finished_at = now_tz()
            run.updated_at = run.finished_at
            db.commit()


def execute_experiment_run(run_id: str) -> None:
    with SessionLocal() as db:
        run = db.execute(select(ExperimentRun).where(ExperimentRun.id == run_id)).scalar_one_or_none()
        if run is None:
            return

        run.status = RunStatus.RUNNING
        run.started_at = now_tz()
        run.updated_at = run.started_at
        db.commit()

        payload = dict(run.request_payload)
        try:
            if run.kind == ExperimentKind.OPTIMIZER:
                optimizer = MultiStrategyOptimizer(
                    symbol=payload["symbol"],
                    start_date=payload["start_date"],
                    end_date=payload["end_date"],
                    provider_name=payload["provider_name"],
                )
                df = optimizer.search(
                    strategy_names=[payload["strategy_name"]],
                    top_n=int(payload.get("top_n", 10)),
                )

                records = df.to_dict(orient="records") if not df.empty else []
                run.response_payload = {
                    "kind": "optimizer",
                    "rows": records,
                    "count": len(records),
                }

                top = records[0] if records else {}
                db.add(
                    RunMetricSnapshot(
                        run_type="experiment",
                        run_id=run.id,
                        experiment_run_id=run.id,
                        cagr=float(top.get("annual_return", 0.0)) / 100 if top else None,
                        max_drawdown=float(top.get("max_drawdown", 0.0)) / 100 if top else None,
                        sharpe=float(top.get("sharpe_ratio", 0.0)) if top else None,
                        annual_turnover=None,
                        data_years=None,
                        metadata_payload={"top": top, "count": len(records)},
                        created_at=now_tz(),
                    )
                )

            else:
                engine = WalkForwardEngine(
                    symbol=payload["symbol"],
                    provider_name=payload["provider_name"],
                    strategy_name=payload["strategy_name"],
                    train_months=int(payload.get("train_months", 12)),
                    test_months=int(payload.get("test_months", 3)),
                    step_months=int(payload.get("step_months", 3)),
                )
                result = engine.run(
                    start_date=payload["start_date"],
                    end_date=payload["end_date"],
                )
                run.response_payload = {
                    "kind": "walkforward",
                    "summary": result.summary,
                    "windows": [window.__dict__ for window in result.windows],
                }
                db.add(
                    RunMetricSnapshot(
                        run_type="experiment",
                        run_id=run.id,
                        experiment_run_id=run.id,
                        cagr=result.summary.get("avg_return", 0.0) / 100 if result.summary else None,
                        max_drawdown=result.summary.get("avg_max_drawdown", 0.0) / 100 if result.summary else None,
                        sharpe=result.summary.get("avg_sharpe") if result.summary else None,
                        annual_turnover=None,
                        data_years=None,
                        metadata_payload=result.summary,
                        created_at=now_tz(),
                    )
                )

            run.status = RunStatus.SUCCEEDED
            run.finished_at = now_tz()
            run.updated_at = run.finished_at
            db.commit()

        except Exception as exc:
            run.status = RunStatus.FAILED
            run.error_message = str(exc)
            run.finished_at = now_tz()
            run.updated_at = run.finished_at
            db.commit()


def get_running_jobs_count(db: Session) -> int:
    return int(
        db.execute(
            select(func.count()).select_from(BacktestRun).where(BacktestRun.status == RunStatus.RUNNING)
        ).scalar_one()
    ) + int(
        db.execute(
            select(func.count()).select_from(ExperimentRun).where(ExperimentRun.status == RunStatus.RUNNING)
        ).scalar_one()
    )


def get_backtest_run_with_metrics(db: Session, run_id: str) -> BacktestRun | None:
    return db.execute(
        select(BacktestRun)
        .options(selectinload(BacktestRun.metric_snapshots))
        .where(BacktestRun.id == run_id)
    ).scalar_one_or_none()


def list_backtest_runs_with_metrics(db: Session, limit: int = 100) -> list[BacktestRun]:
    return list(
        db.execute(
            select(BacktestRun)
            .options(selectinload(BacktestRun.metric_snapshots))
            .order_by(BacktestRun.created_at.desc())
            .limit(limit)
        ).scalars()
    )


def get_experiment_run_with_metrics(db: Session, run_id: str) -> ExperimentRun | None:
    return db.execute(
        select(ExperimentRun)
        .options(selectinload(ExperimentRun.metric_snapshots))
        .where(ExperimentRun.id == run_id)
    ).scalar_one_or_none()


def list_experiment_runs_with_metrics(db: Session, limit: int = 100) -> list[ExperimentRun]:
    return list(
        db.execute(
            select(ExperimentRun)
            .options(selectinload(ExperimentRun.metric_snapshots))
            .order_by(ExperimentRun.created_at.desc())
            .limit(limit)
        ).scalars()
    )
