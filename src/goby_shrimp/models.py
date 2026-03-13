from __future__ import annotations
from enum import Enum
from pydantic import BaseModel, Field


class Verdict(str, Enum):
    GO = "GO"
    NO_GO = "NO_GO"
    REVISE = "REVISE"


class BacktestResult(BaseModel):
    cagr: float
    max_drawdown: float = Field(..., ge=0, le=1)
    sharpe: float
    annual_turnover: float = 0
    data_years: float = Field(..., gt=0)
    assumptions: list[str] = Field(default_factory=list)
    param_sensitivity: float | None = None
    is_first_live: bool = False


class ReviewOutput(BaseModel):
    verdict: Verdict
    requires_human_approve: bool = False
    hard_gates_failed: list[str] = Field(default_factory=list)
    yellow_flags_triggered: list[str] = Field(default_factory=list)
    utility_score: float | None = None
    reasoning: str = ""


class WalkForwardResult(BaseModel):
    """Walk-forward 验证结果"""
    ticker: str
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    
    train_cagr: float
    train_sharpe: float
    train_maxdd: float
    
    test_cagr: float
    test_sharpe: float
    test_maxdd: float
    
    degradation_ratio: float  # test_sharpe / train_sharpe
    is_robust: bool  # degradation_ratio >= 0.5


class PMDecision(BaseModel):
    verdict: Verdict
    utility_score: float
    weights: dict[str, float]
    weight_adjust_reason: str | None = None
    reasoning: str
    risk_warnings: list[str] = Field(default_factory=list)
    next_experiments: list[dict[str, str]] = Field(
        default_factory=list,
        max_length=2
    )
    requires_human_approve: bool = False
