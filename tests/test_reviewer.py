import pytest
from openhamster.models import BacktestResult, Verdict
from openhamster.risk.reviewer import risk_gate_review

FULL = ["slippage", "commission", "tax", "dividend_withholding"]


def make(**kw):
    defaults = {
        "cagr": 0.15,
        "max_drawdown": 0.10,
        "sharpe": 1.2,
        "annual_turnover": 2.0,
        "data_years": 5,
        "assumptions": FULL,
    }
    defaults.update(kw)
    return BacktestResult(**defaults)


def test_max_dd_no_go():
    assert risk_gate_review(make(max_drawdown=0.25)).verdict == Verdict.NO_GO


def test_missing_assumptions_no_go():
    assert risk_gate_review(make(assumptions=["slippage"])).verdict == Verdict.NO_GO


def test_short_data_no_go():
    assert risk_gate_review(make(data_years=2)).verdict == Verdict.NO_GO


def test_dd_near_redline_triggers_approve():
    assert risk_gate_review(make(max_drawdown=0.13)).requires_human_approve


def test_high_cagr_triggers_approve():
    assert risk_gate_review(make(cagr=0.50)).requires_human_approve


def test_first_live_triggers_approve():
    assert risk_gate_review(make(is_first_live=True)).requires_human_approve


def test_good_strategy_go():
    out = risk_gate_review(make(cagr=0.15, max_drawdown=0.08, sharpe=1.5))
    assert out.verdict == Verdict.GO
    assert not out.requires_human_approve
