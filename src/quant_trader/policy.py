from __future__ import annotations
from pathlib import Path
from dataclasses import dataclass, field
import yaml


@dataclass(frozen=True)
class HardGates:
    max_drawdown: float = 0.20
    min_data_years: int = 3
    required_assumptions: list[str] = field(
        default_factory=lambda: [
            "slippage",
            "commission",
            "tax",
            "dividend_withholding"
        ]
    )


@dataclass(frozen=True)
class YellowFlags:
    max_drawdown_warning_range: tuple[float, float] = (0.15, 0.20)
    suspiciously_high_cagr: float = 0.40
    param_sensitivity_threshold: float = 0.50
    first_live_deployment: bool = True


@dataclass(frozen=True)
class Weights:
    cagr: float = 0.35
    max_dd: float = 0.35
    sharpe: float = 0.20
    turnover: float = 0.10
    adjust_range: float = 0.10


@dataclass(frozen=True)
class Limits:
    max_debate_rounds: int = 2
    max_iterations: int = 3
    on_max_reached: str = "STOP_AND_NOTIFY_HUMAN"


@dataclass(frozen=True)
class TradingCosts:
    """交易成本假设"""
    slippage_bps: float = 5        # 滑点 (basis points)
    commission_rate: float = 0.001 # 佣金率
    tax_rate: float = 0.001        # 印花税率
    dividend_withholding: float = 0.15 # 股息预扣税率


@dataclass(frozen=True)
class NotificationConfig:
    """通知配置"""
    enabled: bool = False
    chat_id: str = ""
    # Email specific
    smtp_host: str = ""
    smtp_port: int = 587
    from_addr: str = ""
    to_addrs: list = field(default_factory=list)


@dataclass(frozen=True)
class Notifications:
    """通知配置"""
    telegram: NotificationConfig = field(default_factory=NotificationConfig)
    email: NotificationConfig = field(default_factory=NotificationConfig)


@dataclass(frozen=True)
class Policy:
    hard_gates: HardGates = field(default_factory=HardGates)
    yellow_flags: YellowFlags = field(default_factory=YellowFlags)
    weights: Weights = field(default_factory=Weights)
    limits: Limits = field(default_factory=Limits)
    trading_costs: TradingCosts = field(default_factory=TradingCosts)
    notifications: Notifications = field(default_factory=Notifications)


def load_policy(config_path=None) -> Policy:
    if config_path is None:
        config_path = (
            Path(__file__).parent.parent.parent / "config" / "policy.yaml"
        )
    config_path = Path(config_path)
    if not config_path.exists():
        return Policy()

    with open(config_path) as f:
        raw = yaml.safe_load(f)

    return Policy(
        hard_gates=HardGates(**raw.get("hard_gates", {})),
        yellow_flags=YellowFlags(
            **{k: tuple(v) if isinstance(v, list) else v
               for k, v in raw.get("yellow_flags", {}).items()}
        ),
        weights=Weights(**raw.get("weights", {})),
        limits=Limits(**raw.get("limits", {})),
        trading_costs=TradingCosts(**raw.get("trading_costs", {})),
        notifications=Notifications(
            telegram=NotificationConfig(**raw.get("notifications", {}).get("telegram", {})),
            email=NotificationConfig(**raw.get("notifications", {}).get("email", {})),
        ),
    )


policy = load_policy()
