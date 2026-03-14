from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class DataSourceSettings(BaseModel):
    provider: str = "akshare"
    fallback: list[str] = Field(default_factory=lambda: ["stooq"])
    cache_enabled: bool = True


class EventsSettings(BaseModel):
    macro_provider: str = "demo_macro"
    fallback_mode: str = "reuse_last_good"
    fallback_max_age_days: int = 14
    expected_sync_interval_minutes: int = 60


class LLMSettings(BaseModel):
    provider: str = "minimax"
    model: str = "MiniMax-M2.5"
    temperature: float = 0.3
    max_output_tokens: int = 4096


class StrategySettings(BaseModel):
    mode: str = "auto"
    enabled: list[str] = Field(
        default_factory=lambda: ["ma_cross", "rsi", "macd", "mean_reversion", "channel_breakout"]
    )
    manual_primary: str = "ma_cross"
    default_params: dict[str, Any] = Field(default_factory=dict)


class UniverseSettings(BaseModel):
    mode: str = "dynamic_hk"
    top_n: int = 20
    min_list_days: int = 120
    exclude_st: bool = True
    include_gem: bool = True
    min_turnover_millions: float = 200.0


class ExecutionRulesSettings(BaseModel):
    allow_short: bool = False
    cn_lot_size: int = 100
    cn_t_plus_one: bool = False


class PortfolioSettings(BaseModel):
    symbols: list[str] = Field(default_factory=lambda: ["2800.HK"])
    default_capital: int = 1_000_000


class TradingCostsSettings(BaseModel):
    slippage_bps: float = 5
    commission_rate: float = 0.0003
    tax_rate: float = 0.001
    dividend_withholding: float = 0.0


class HardGatesSettings(BaseModel):
    max_drawdown: float = 0.15
    min_data_years: int = 3
    required_assumptions: list[str] = Field(
        default_factory=lambda: ["slippage", "commission", "tax", "dividend_withholding"]
    )


class YellowFlagsSettings(BaseModel):
    max_drawdown_warning_range: tuple[float, float] = (0.12, 0.15)
    suspiciously_high_cagr: float = 0.40
    param_sensitivity_threshold: float = 0.50
    first_live_deployment: bool = True


class GovernanceSettings(BaseModel):
    promote_threshold: float = 75.0
    keep_threshold: float = 68.0
    challenger_min_delta: float = 3.0
    cooldown_days: int = 5
    live_drawdown_pause: float = 0.12
    live_drawdown_rollback: float = 0.15
    acceptance_min_days: int = 7
    acceptance_min_fill_rate: float = 0.6
    acceptance_max_drawdown: float = 0.08
    block_promotion_on_macro_degrade: bool = True


class WeightsSettings(BaseModel):
    cagr: float = 0.35
    max_dd: float = 0.35
    sharpe: float = 0.20
    turnover: float = 0.10


class LimitsSettings(BaseModel):
    max_debate_rounds: int = 2
    max_iterations: int = 3


class IntegrationsSettings(BaseModel):
    minimax_api_key: str = ""
    fred_api_key: str = ""
    twelve_data_api_key: str = ""
    tushare_token: str = ""
    alphavantage_api_key: str = ""
    itick_token: str = ""


class StorageSettings(BaseModel):
    database_url: str = "sqlite:///var/db/goby_shrimp.db"
    runtime_db_path: str = "var/db/trading.db"
    paper_db_path: str = "var/db/paper_trading.db"
    runtime_state_db_path: str = "var/db/runtime_state.db"
    market_cache_path: str = "var/cache/market_data_cache.db"
    log_path: str = "var/logs/goby_shrimp.log"


class AppSettings(BaseModel):
    app_name: str = "GobyShrimp"
    timezone: str = "Asia/Shanghai"
    env: str = "local"

    data_source: DataSourceSettings = Field(default_factory=DataSourceSettings)
    events: EventsSettings = Field(default_factory=EventsSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    strategy: StrategySettings = Field(default_factory=StrategySettings)
    universe: UniverseSettings = Field(default_factory=UniverseSettings)
    execution_rules: ExecutionRulesSettings = Field(default_factory=ExecutionRulesSettings)
    portfolio: PortfolioSettings = Field(default_factory=PortfolioSettings)
    trading_costs: TradingCostsSettings = Field(default_factory=TradingCostsSettings)
    hard_gates: HardGatesSettings = Field(default_factory=HardGatesSettings)
    yellow_flags: YellowFlagsSettings = Field(default_factory=YellowFlagsSettings)
    governance: GovernanceSettings = Field(default_factory=GovernanceSettings)
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
    "RUNTIME_STATE_DB_PATH": "storage.runtime_state_db_path",
    "MARKET_CACHE_PATH": "storage.market_cache_path",
    "APP_LOG_PATH": "storage.log_path",
    "LLM_PROVIDER": "llm.provider",
    "LLM_MODEL": "llm.model",
    "LLM_TEMPERATURE": "llm.temperature",
    "LLM_MAX_OUTPUT_TOKENS": "llm.max_output_tokens",
    "MINIMAX_API_KEY": "integrations.minimax_api_key",
    "FRED_API_KEY": "integrations.fred_api_key",
    "TWELVE_DATA_API_KEY": "integrations.twelve_data_api_key",
    "TUSHARE_TOKEN": "integrations.tushare_token",
    "ALPHAVANTAGE_API_KEY": "integrations.alphavantage_api_key",
    "ITICK_TOKEN": "integrations.itick_token",
}


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file) or {}


def _read_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        values[key] = value
    return values


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

    env_file_paths = [Path(".env"), Path(".env.local")]
    for env_file_path in env_file_paths:
        env_data = _read_env_file(env_file_path)
        for env_name, raw in env_data.items():
            path = ENV_MAPPING.get(env_name)
            if path is None:
                continue
            _set_path(merged, path, _coerce_env(raw))
            source_map[path] = "env_file"

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
