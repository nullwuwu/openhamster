from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class BrokerSettings(BaseModel):
    type: str = "paper"
    mode: str = "dry_run"
    max_order_value: int = 500000
    require_confirm_live: bool = True


class SchedulerSettings(BaseModel):
    enabled: bool = True
    run_time: str = "15:10"
    timezone: str = "Asia/Shanghai"


class DataSourceSettings(BaseModel):
    provider: str = "akshare"
    fallback: list[str] = Field(default_factory=lambda: ["stooq"])
    cache_enabled: bool = True


class StrategySettings(BaseModel):
    mode: str = "auto"
    enabled: list[str] = Field(
        default_factory=lambda: ["ma_cross", "rsi", "macd", "mean_reversion", "channel_breakout"]
    )
    manual_primary: str = "ma_cross"
    default_params: dict[str, Any] = Field(default_factory=dict)


class UniverseSettings(BaseModel):
    mode: str = "dynamic_cn"
    top_n: int = 20
    min_list_days: int = 120
    exclude_st: bool = True
    include_gem: bool = True


class ExecutionRulesSettings(BaseModel):
    allow_short: bool = False
    cn_lot_size: int = 100
    cn_t_plus_one: bool = True


class PortfolioSettings(BaseModel):
    symbols: list[str] = Field(default_factory=lambda: ["000300.SH", "510300.SH", "159915.SZ"])
    default_capital: int = 1_000_000


class NotificationChannelSettings(BaseModel):
    enabled: bool = False
    chat_id: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    from_addr: str = ""
    to_addrs: list[str] = Field(default_factory=list)


class NotificationsSettings(BaseModel):
    telegram: NotificationChannelSettings = Field(default_factory=NotificationChannelSettings)
    email: NotificationChannelSettings = Field(default_factory=NotificationChannelSettings)


class TradingCostsSettings(BaseModel):
    slippage_bps: float = 5
    commission_rate: float = 0.0003
    tax_rate: float = 0.001
    dividend_withholding: float = 0.0


class HardGatesSettings(BaseModel):
    max_drawdown: float = 0.20
    min_data_years: int = 3
    required_assumptions: list[str] = Field(
        default_factory=lambda: ["slippage", "commission", "tax", "dividend_withholding"]
    )


class YellowFlagsSettings(BaseModel):
    max_drawdown_warning_range: tuple[float, float] = (0.15, 0.20)
    suspiciously_high_cagr: float = 0.40
    param_sensitivity_threshold: float = 0.50
    first_live_deployment: bool = True


class WeightsSettings(BaseModel):
    cagr: float = 0.35
    max_dd: float = 0.35
    sharpe: float = 0.20
    turnover: float = 0.10
    adjust_range: float = 0.10


class LimitsSettings(BaseModel):
    max_debate_rounds: int = 2
    max_iterations: int = 3
    on_max_reached: str = "STOP_AND_NOTIFY_HUMAN"


class IntegrationsSettings(BaseModel):
    minimax_api_key: str = ""
    twelve_data_api_key: str = ""
    tushare_token: str = ""
    alphavantage_api_key: str = ""
    itick_token: str = ""
    longbridge_app_key: str = ""
    longbridge_app_secret: str = ""
    longbridge_access_token: str = ""


class StorageSettings(BaseModel):
    database_url: str = "sqlite:///var/db/quant_trader.db"
    runtime_db_path: str = "var/db/trading.db"
    paper_db_path: str = "var/db/paper_trading.db"
    market_cache_path: str = "var/cache/market_data_cache.db"
    log_path: str = "var/logs/quant_trader.log"


class AppSettings(BaseModel):
    app_name: str = "quant-trader"
    timezone: str = "Asia/Shanghai"
    env: str = "local"

    broker: BrokerSettings = Field(default_factory=BrokerSettings)
    scheduler: SchedulerSettings = Field(default_factory=SchedulerSettings)
    data_source: DataSourceSettings = Field(default_factory=DataSourceSettings)
    strategy: StrategySettings = Field(default_factory=StrategySettings)
    universe: UniverseSettings = Field(default_factory=UniverseSettings)
    execution_rules: ExecutionRulesSettings = Field(default_factory=ExecutionRulesSettings)
    portfolio: PortfolioSettings = Field(default_factory=PortfolioSettings)
    notifications: NotificationsSettings = Field(default_factory=NotificationsSettings)
    trading_costs: TradingCostsSettings = Field(default_factory=TradingCostsSettings)
    hard_gates: HardGatesSettings = Field(default_factory=HardGatesSettings)
    yellow_flags: YellowFlagsSettings = Field(default_factory=YellowFlagsSettings)
    weights: WeightsSettings = Field(default_factory=WeightsSettings)
    limits: LimitsSettings = Field(default_factory=LimitsSettings)
    integrations: IntegrationsSettings = Field(default_factory=IntegrationsSettings)
    storage: StorageSettings = Field(default_factory=StorageSettings)


ENV_MAPPING: dict[str, str] = {
    "APP_ENV": "env",
    "APP_TIMEZONE": "timezone",
    "DATABASE_URL": "storage.database_url",
    "RUNTIME_DB_PATH": "storage.runtime_db_path",
    "PAPER_DB_PATH": "storage.paper_db_path",
    "MARKET_CACHE_PATH": "storage.market_cache_path",
    "APP_LOG_PATH": "storage.log_path",
    "MINIMAX_API_KEY": "integrations.minimax_api_key",
    "TWELVE_DATA_API_KEY": "integrations.twelve_data_api_key",
    "TUSHARE_TOKEN": "integrations.tushare_token",
    "ALPHAVANTAGE_API_KEY": "integrations.alphavantage_api_key",
    "ITICK_TOKEN": "integrations.itick_token",
    "LONGBRIDGE_APP_KEY": "integrations.longbridge_app_key",
    "LONGBRIDGE_APP_SECRET": "integrations.longbridge_app_secret",
    "LONGBRIDGE_ACCESS_TOKEN": "integrations.longbridge_access_token",
}


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file) or {}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in override.items():
        current = out.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            out[key] = _deep_merge(current, value)
        else:
            out[key] = value
    return out


def _flatten(data: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in data.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            out.update(_flatten(value, path))
        else:
            out[path] = value
    return out


def _set_path(data: dict[str, Any], dotted_path: str, value: Any) -> None:
    keys = dotted_path.split(".")
    cursor = data
    for key in keys[:-1]:
        if key not in cursor or not isinstance(cursor[key], dict):
            cursor[key] = {}
        cursor = cursor[key]
    cursor[keys[-1]] = value


def _coerce_env(value: str) -> Any:
    text = value.strip()
    if text.lower() in {"true", "false"}:
        return text.lower() == "true"
    try:
        if "." in text:
            return float(text)
        return int(text)
    except ValueError:
        pass

    if text.startswith("[") and text.endswith("]"):
        parsed = yaml.safe_load(text)
        if isinstance(parsed, list):
            return parsed

    return text


def load_app_settings(
    base_path: str | Path = "config/base.yaml",
    local_path: str | Path = "config/local.yaml",
) -> tuple[AppSettings, dict[str, str]]:
    default_data = AppSettings().model_dump(mode="python")
    source_map: dict[str, str] = dict.fromkeys(_flatten(default_data), "default")

    base_data = _read_yaml(Path(base_path))
    if base_data:
        for key in _flatten(base_data):
            source_map[key] = "base"

    local_data = _read_yaml(Path(local_path))
    if local_data:
        for key in _flatten(local_data):
            source_map[key] = "local"

    merged = _deep_merge(default_data, base_data)
    merged = _deep_merge(merged, local_data)

    for env_name, path in ENV_MAPPING.items():
        raw = os.getenv(env_name)
        if raw is None:
            continue
        _set_path(merged, path, _coerce_env(raw))
        source_map[path] = "env"

    settings = AppSettings.model_validate(merged)
    return settings, source_map


_SETTINGS: AppSettings | None = None
_SOURCE_MAP: dict[str, str] = {}


def get_settings() -> AppSettings:
    global _SETTINGS, _SOURCE_MAP
    if _SETTINGS is None:
        _SETTINGS, _SOURCE_MAP = load_app_settings()
    return _SETTINGS


def get_settings_source_map() -> dict[str, str]:
    if not _SOURCE_MAP:
        get_settings()
    return dict(_SOURCE_MAP)


def get_setting_source(dotted_path: str) -> str:
    source_map = get_settings_source_map()
    return source_map.get(dotted_path, "unknown")


def reload_settings() -> AppSettings:
    global _SETTINGS, _SOURCE_MAP
    _SETTINGS, _SOURCE_MAP = load_app_settings()
    return _SETTINGS
