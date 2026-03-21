from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class GovernanceProfile:
    promote_threshold: float
    keep_threshold: float
    challenger_min_delta: float
    cooldown_days: int
    acceptance_min_days: int
    acceptance_min_fill_rate: float
    acceptance_max_drawdown: float
    live_drawdown_pause: float
    live_drawdown_rollback: float


@dataclass(frozen=True)
class MarketProfile:
    market_scope: str
    label: str
    timezone: str
    benchmark_symbol: str
    trading_style: str
    structure_notes: list[str]
    preferred_baseline_tags: list[str]
    discouraged_baseline_tags: list[str]
    execution_constraints: list[str]
    governance: GovernanceProfile

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["structure_notes"] = list(self.structure_notes)
        payload["preferred_baseline_tags"] = list(self.preferred_baseline_tags)
        payload["discouraged_baseline_tags"] = list(self.discouraged_baseline_tags)
        payload["execution_constraints"] = list(self.execution_constraints)
        return payload


MARKET_PROFILES: dict[str, MarketProfile] = {
    "HK": MarketProfile(
        market_scope="HK",
        label="Hong Kong cash equity / ETF profile",
        timezone="Asia/Hong_Kong",
        benchmark_symbol="2800.HK",
        trading_style="index-led, macro-sensitive, lower-retail-noise",
        structure_notes=[
            "Index and ETF leadership dominate broad tape direction.",
            "Macro liquidity and USD-linked financial conditions matter more than retail sentiment bursts.",
            "Daily execution should prefer lower-turnover, more patient entries than CN retail-driven rotation trades.",
        ],
        preferred_baseline_tags=["trend", "moving-average", "breakout", "vectorized"],
        discouraged_baseline_tags=["mean-reversion", "oscillator"],
        execution_constraints=[
            "cash_equity_only",
            "daily_rebalance_only",
            "single_active_strategy",
            "respect_hk_lot_and_fee_assumptions",
        ],
        governance=GovernanceProfile(
            promote_threshold=76.0,
            keep_threshold=69.0,
            challenger_min_delta=2.5,
            cooldown_days=4,
            acceptance_min_days=8,
            acceptance_min_fill_rate=0.55,
            acceptance_max_drawdown=0.09,
            live_drawdown_pause=0.10,
            live_drawdown_rollback=0.13,
        ),
    ),
    "CN": MarketProfile(
        market_scope="CN",
        label="China A-share cash equity profile",
        timezone="Asia/Shanghai",
        benchmark_symbol="000300.SH",
        trading_style="rotation-heavy, retail-sensitive, regime-switching",
        structure_notes=[
            "Retail-driven rotation and sector bursts are more frequent.",
            "Execution and turnover assumptions need more caution around T+1 and lot-size constraints.",
            "Reversion and oscillator ideas are more admissible than in HK, but still need hard risk control.",
        ],
        preferred_baseline_tags=["momentum", "oscillator", "reversion"],
        discouraged_baseline_tags=["slow-trend"],
        execution_constraints=[
            "cash_equity_only",
            "daily_rebalance_only",
            "single_active_strategy",
            "respect_cn_t_plus_one",
        ],
        governance=GovernanceProfile(
            promote_threshold=75.0,
            keep_threshold=68.0,
            challenger_min_delta=3.0,
            cooldown_days=5,
            acceptance_min_days=7,
            acceptance_min_fill_rate=0.60,
            acceptance_max_drawdown=0.08,
            live_drawdown_pause=0.12,
            live_drawdown_rollback=0.15,
        ),
    ),
}


def get_market_profile(market_scope: str) -> MarketProfile:
    normalized = market_scope.upper()
    return MARKET_PROFILES.get(normalized, MARKET_PROFILES["HK"])
