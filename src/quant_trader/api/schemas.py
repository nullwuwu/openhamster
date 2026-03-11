from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from .models import ExperimentKind, RunStatus


class BacktestRunCreate(BaseModel):
    symbol: str = Field(default="000300.SH", min_length=1, max_length=32)
    strategy_name: str = Field(default="ma_cross", min_length=1, max_length=64)
    provider_name: str = Field(default="stooq", min_length=1, max_length=64)
    start_date: str = "2020-01-01"
    end_date: str | None = None
    initial_capital: float = 100000
    is_first_live: bool = False
    strategy_params: dict[str, Any] = Field(default_factory=dict)


class ExperimentRunCreate(BaseModel):
    symbol: str = Field(default="000300.SH", min_length=1, max_length=32)
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
    updated_at: datetime


class OverviewDTO(BaseModel):
    generated_at: datetime
    timezone: str
    total_backtest_runs: int
    total_experiment_runs: int
    running_jobs: int
    latest_backtest: BacktestRunDTO | None = None
    latest_experiment: ExperimentRunDTO | None = None
    latest_total_equity: float | None = None
    latest_trade_date: str | None = None


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


class PaperTradingDTO(BaseModel):
    nav: list[PaperNavPointDTO] = Field(default_factory=list)
    orders: list[PaperOrderDTO] = Field(default_factory=list)
    positions: list[PaperPositionDTO] = Field(default_factory=list)


class CreatedRunResponse(BaseModel):
    run_id: str
    status: Literal["queued"]
