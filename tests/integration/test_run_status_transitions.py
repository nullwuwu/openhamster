from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select

from quant_trader.api.db import SessionLocal, init_database
from quant_trader.api.models import BacktestRun, RunStatus
from quant_trader.api.services import execute_backtest_run, now_tz


def _create_run() -> str:
    with SessionLocal() as db:
        run = BacktestRun(
            symbol='000300.SH',
            strategy_name='ma_cross',
            provider_name='stooq',
            status=RunStatus.QUEUED,
            request_payload={
                'symbol': '000300.SH',
                'strategy_name': 'ma_cross',
                'provider_name': 'stooq',
                'start_date': '2020-01-01',
                'end_date': '2020-02-01',
                'initial_capital': 100000,
                'strategy_params': {},
            },
            created_at=now_tz(),
            updated_at=now_tz(),
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        return run.id


@dataclass
class DummyBacktestResult:
    cagr: float = 0.1
    max_drawdown: float = 0.05
    sharpe: float = 1.2
    annual_turnover: float = 0.3
    data_years: float = 3.0
    assumptions: list[str] = None
    param_sensitivity: float = 0.1

    def __post_init__(self) -> None:
        if self.assumptions is None:
            self.assumptions = ['slippage', 'commission', 'tax', 'dividend_withholding']

    def model_dump(self) -> dict:
        return {
            'cagr': self.cagr,
            'max_drawdown': self.max_drawdown,
            'sharpe': self.sharpe,
            'annual_turnover': self.annual_turnover,
            'data_years': self.data_years,
            'assumptions': self.assumptions,
            'param_sensitivity': self.param_sensitivity,
            'is_first_live': False,
        }


class DummyBacktestEngine:
    def __init__(self, data_provider=None):
        self.data_provider = data_provider

    def run(self, **kwargs):
        return DummyBacktestResult()


class DummyFactory:
    def create(self, **kwargs):
        return object()


def test_execute_backtest_run_succeeded(monkeypatch) -> None:
    init_database()
    run_id = _create_run()

    monkeypatch.setattr('quant_trader.api.services.BacktestEngine', DummyBacktestEngine)
    monkeypatch.setattr('quant_trader.api.services.get_strategy_factory', lambda: DummyFactory())
    monkeypatch.setattr('quant_trader.api.services.get_provider', lambda _: None)

    execute_backtest_run(run_id)

    with SessionLocal() as db:
        run = db.execute(select(BacktestRun).where(BacktestRun.id == run_id)).scalar_one()
        assert run.status == RunStatus.SUCCEEDED
        assert run.response_payload is not None
        assert run.finished_at is not None


def test_execute_backtest_run_failed(monkeypatch) -> None:
    init_database()
    run_id = _create_run()

    class BrokenEngine:
        def __init__(self, data_provider=None):
            self.data_provider = data_provider

        def run(self, **kwargs):
            raise RuntimeError('boom')

    monkeypatch.setattr('quant_trader.api.services.BacktestEngine', BrokenEngine)
    monkeypatch.setattr('quant_trader.api.services.get_strategy_factory', lambda: DummyFactory())
    monkeypatch.setattr('quant_trader.api.services.get_provider', lambda _: None)

    execute_backtest_run(run_id)

    with SessionLocal() as db:
        run = db.execute(select(BacktestRun).where(BacktestRun.id == run_id)).scalar_one()
        assert run.status == RunStatus.FAILED
        assert run.error_message is not None
