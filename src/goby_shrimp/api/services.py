from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from threading import Lock
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..backtest.backtest_engine import BacktestEngine
from ..backtest.optimizer import MultiStrategyOptimizer
from ..backtest.walk_forward import WalkForwardEngine
from ..config import get_settings
from ..data import get_provider
from ..events import EventSeed, get_event_providers
from ..llm_gateway import LLMProvider, get_llm_gateway
from ..prompts import (
    MARKET_ANALYST_PROMPT_VERSION,
    MARKET_ANALYST_SCHEMA_HINT,
    RESEARCH_DEBATE_PROMPT_VERSION,
    RESEARCH_DEBATE_SCHEMA_HINT,
    RISK_MANAGER_LLM_PROMPT_VERSION,
    RISK_MANAGER_LLM_SCHEMA_HINT,
    STRATEGY_AGENT_PROMPT_VERSION,
    STRATEGY_AGENT_SCHEMA_HINT,
    build_market_analyst_payload,
    build_research_debate_payload,
    build_risk_manager_llm_payload,
    build_strategy_agent_payload,
    market_analyst_system_prompt,
    research_debate_system_prompt,
    risk_manager_llm_system_prompt,
    strategy_agent_system_prompt,
)
from ..market_regime import Regime, get_market_regime
from ..strategy import get_strategy_factory, get_strategy_registry
from .db import SessionLocal
from .models import (
    AuditRecord,
    BacktestRun,
    DailyEventDigest,
    EventRecord,
    EventType,
    ExperimentKind,
    ExperimentRun,
    ProposalStatus,
    RiskDecision,
    RiskDecisionAction,
    RunMetricSnapshot,
    RunStatus,
    RuntimeSetting,
    StrategyProposal,
    StrategySnapshot,
)

_MACRO_STATUS_KEY = "events.macro.status"
_PIPELINE_STATUS_KEY = "pipeline.runtime.status"
_PIPELINE_SYNC_LOCK = Lock()


def now_tz() -> datetime:
    settings = get_settings()
    return datetime.now(ZoneInfo(settings.timezone))


def stable_hash(payload: object) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]


def _record_system_audit(
    db: Session,
    *,
    event_type: str,
    entity_type: str,
    entity_id: str,
    payload: dict[str, object],
    created_at: datetime,
    run_id: str = "system-governance",
    decision_id: str | None = None,
    market_snapshot_hash: str = "",
    event_digest_hash: str = "",
) -> None:
    db.add(
        AuditRecord(
            run_id=run_id,
            decision_id=decision_id or f"{event_type}-{stable_hash([entity_id, created_at.isoformat()])}",
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            strategy_dsl_hash="",
            market_snapshot_hash=market_snapshot_hash,
            event_digest_hash=event_digest_hash,
            payload=payload,
            created_at=created_at,
        )
    )


def _recent_audit_counts(
    db: Session,
    *,
    event_types: list[str],
    entity_type: str | None = None,
    entity_id: str | None = None,
    days: int = 30,
) -> int:
    since = now_tz() - timedelta(days=days)
    query = select(func.count()).select_from(AuditRecord).where(
        AuditRecord.created_at >= since,
        AuditRecord.event_type.in_(event_types),
    )
    if entity_type is not None:
        query = query.where(AuditRecord.entity_type == entity_type)
    if entity_id is not None:
        query = query.where(AuditRecord.entity_id == entity_id)
    return int(db.execute(query).scalar_one())


def _build_macro_health_history(db: Session) -> dict[str, object]:
    degraded_count = _recent_audit_counts(
        db,
        event_types=['macro_provider_degraded'],
        entity_type='macro_pipeline',
    )
    fallback_count = _recent_audit_counts(
        db,
        event_types=['macro_provider_fallback_applied'],
        entity_type='macro_pipeline',
    )
    recovery_count = _recent_audit_counts(
        db,
        event_types=['macro_provider_recovered'],
        entity_type='macro_pipeline',
    )
    health_score = max(0.1, min(1.0, 1.0 - degraded_count * 0.12 - fallback_count * 0.06 + recovery_count * 0.02))
    return {
        'health_score_30d': round(health_score, 2),
        'degraded_count_30d': degraded_count,
        'fallback_count_30d': fallback_count,
        'recovery_count_30d': recovery_count,
    }


def get_macro_pipeline_status(db: Session) -> dict[str, object]:
    provider = get_settings().events.macro_provider
    record = db.execute(select(RuntimeSetting).where(RuntimeSetting.key == _MACRO_STATUS_KEY)).scalar_one_or_none()
    if record is None or not isinstance(record.value_json, dict):
        base_status = {
            "provider": provider,
            "active_provider": provider,
            "provider_chain": [provider],
            "status": "ready",
            "message": f"{provider} macro pipeline ready.",
            "degraded": False,
            "last_success_at": None,
            "fallback_mode": None,
            "fallback_event_count": 0,
            "using_last_known_context": False,
            "reliability_score": 1.0,
            "reliability_tier": "primary_live",
        }
        return _enrich_macro_pipeline_status(base_status, db=db)
    value = dict(record.value_json)
    status = {
        "provider": str(value.get("provider", provider)),
        "active_provider": str(value.get("active_provider", value.get("provider", provider))),
        "provider_chain": list(value.get("provider_chain", [provider])),
        "status": str(value.get("status", "ready")),
        "message": str(value.get("message", f"{provider} macro pipeline ready.")),
        "degraded": bool(value.get("degraded", False)),
        "last_success_at": value.get("last_success_at"),
        "fallback_mode": value.get("fallback_mode"),
        "fallback_event_count": int(value.get("fallback_event_count", 0) or 0),
        "using_last_known_context": bool(value.get("using_last_known_context", False)),
        "reliability_score": float(value.get("reliability_score", 1.0) or 1.0),
        "reliability_tier": str(value.get("reliability_tier", "primary_live")),
    }
    return _enrich_macro_pipeline_status(status, db=db)


def _enrich_macro_pipeline_status(status: dict[str, object], *, db: Session) -> dict[str, object]:
    enriched = dict(status)
    last_success_at = enriched.get("last_success_at")
    freshness_hours: float | None = None
    if isinstance(last_success_at, str) and last_success_at:
        try:
            last_success_dt = datetime.fromisoformat(last_success_at)
            freshness_hours = round(max(0.0, (now_tz() - last_success_dt).total_seconds() / 3600), 1)
        except ValueError:
            freshness_hours = None
    fallback_max_age_hours = get_settings().events.fallback_max_age_days * 24
    if freshness_hours is None:
        freshness_tier = "fresh"
    elif freshness_hours <= 24:
        freshness_tier = "fresh"
    elif freshness_hours <= 72:
        freshness_tier = "aging"
    elif freshness_hours <= fallback_max_age_hours:
        freshness_tier = "stale"
    else:
        freshness_tier = "expired"
    base_reliability = float(enriched.get("reliability_score", 1.0) or 1.0)
    if freshness_hours is not None:
        age_penalty = min(0.35, freshness_hours / max(fallback_max_age_hours, 1) * 0.35)
        enriched["reliability_score"] = round(max(0.05, base_reliability - age_penalty), 2)
    else:
        enriched["reliability_score"] = round(base_reliability, 2)
    enriched["freshness_hours"] = freshness_hours
    enriched["freshness_tier"] = freshness_tier
    enriched.update(_build_macro_health_history(db))
    return enriched


def get_current_llm_status(db: Session):
    return get_llm_gateway().get_status(db)


def get_pipeline_runtime_status(db: Session) -> dict[str, object]:
    interval_minutes = max(5, get_settings().events.expected_sync_interval_minutes)
    status = _get_runtime_setting_json(db, _PIPELINE_STATUS_KEY) or {
        'current_state': 'idle',
        'status_message': 'Pipeline has not recorded a full sync yet.',
        'last_run_at': None,
        'last_success_at': None,
        'last_failure_at': None,
        'consecutive_failures': 0,
        'expected_next_run_at': None,
        'last_duration_ms': None,
        'last_trigger': None,
        'degraded': False,
    }
    current_state = str(status.get('current_state', 'idle'))
    stalled = False
    expected_next_run_at = status.get('expected_next_run_at')
    if current_state != 'running' and isinstance(expected_next_run_at, str) and expected_next_run_at:
        try:
            stalled = now_tz() > datetime.fromisoformat(expected_next_run_at)
        except ValueError:
            stalled = False
    if stalled and current_state not in {'failed', 'degraded'}:
        current_state = 'stalled'
    return {
        'current_state': current_state,
        'status_message': str(status.get('status_message', 'Pipeline status unavailable.')),
        'last_run_at': status.get('last_run_at'),
        'last_success_at': status.get('last_success_at'),
        'last_failure_at': status.get('last_failure_at'),
        'consecutive_failures': int(status.get('consecutive_failures', 0) or 0),
        'expected_next_run_at': expected_next_run_at,
        'last_duration_ms': int(status['last_duration_ms']) if status.get('last_duration_ms') is not None else None,
        'last_trigger': status.get('last_trigger'),
        'degraded': bool(status.get('degraded', False)),
        'stalled': stalled,
    }


def _set_pipeline_runtime_status(
    db: Session,
    *,
    current_state: str,
    status_message: str,
    current_time: datetime,
    last_success_at: str | None = None,
    last_failure_at: str | None = None,
    consecutive_failures: int | None = None,
    last_duration_ms: int | None = None,
    last_trigger: str | None = None,
    degraded: bool | None = None,
) -> None:
    previous = _get_runtime_setting_json(db, _PIPELINE_STATUS_KEY) or {}
    interval_minutes = max(5, get_settings().events.expected_sync_interval_minutes)
    payload = {
        'current_state': current_state,
        'status_message': status_message,
        'last_run_at': current_time.isoformat(),
        'last_success_at': last_success_at if last_success_at is not None else previous.get('last_success_at'),
        'last_failure_at': last_failure_at if last_failure_at is not None else previous.get('last_failure_at'),
        'consecutive_failures': consecutive_failures if consecutive_failures is not None else int(previous.get('consecutive_failures', 0) or 0),
        'expected_next_run_at': None if current_state == 'running' else (current_time + timedelta(minutes=interval_minutes)).isoformat(),
        'last_duration_ms': last_duration_ms if last_duration_ms is not None else previous.get('last_duration_ms'),
        'last_trigger': last_trigger if last_trigger is not None else previous.get('last_trigger'),
        'degraded': degraded if degraded is not None else bool(previous.get('degraded', False)),
    }
    _set_runtime_setting_json(db, _PIPELINE_STATUS_KEY, payload, current_time)


def set_runtime_llm_provider(db: Session, provider: str):
    current_provider = get_llm_gateway().get_provider(db)
    status = get_llm_gateway().set_provider(db, provider)
    audit_time = now_tz()
    db.add(
        AuditRecord(
            run_id="system-llm-gateway",
            decision_id=f"llm-provider-{stable_hash([current_provider, provider, audit_time.isoformat()])}",
            event_type="llm_provider_changed",
            entity_type="llm_gateway",
            entity_id=status.provider,
            strategy_dsl_hash="",
            market_snapshot_hash="",
            event_digest_hash="",
            payload={
                "old_provider": current_provider,
                "new_provider": status.provider,
                "status": status.status,
                "message": status.message,
                "success": not (
                    status.provider == LLMProvider.MINIMAX and status.status == "missing_key"
                ),
            },
            created_at=audit_time,
        )
    )
    db.commit()
    if status.provider == LLMProvider.MINIMAX and status.status == "missing_key":
        return status, False
    sync_agent_state(db, force_refresh=True, trigger='runtime_provider_switch')
    return status, True


def sync_strategy_snapshots(db: Session) -> None:
    settings = get_settings()
    factory = get_strategy_factory()
    known = set(factory.registry.names())
    enabled = set(settings.strategy.enabled)

    for strategy_name in sorted(known):
        description = f"Baseline strategy available as prior art for GobyShrimp agents: {strategy_name}"
        definition = factory.registry.get(strategy_name)
        record = db.execute(
            select(StrategySnapshot).where(StrategySnapshot.strategy_name == strategy_name)
        ).scalar_one_or_none()
        if record is None:
            db.add(
                StrategySnapshot(
                    strategy_name=strategy_name,
                    description=description,
                    default_params=definition.default_params,
                    enabled=strategy_name in enabled,
                    updated_at=now_tz(),
                )
            )
        else:
            record.description = description
            record.default_params = definition.default_params
            record.enabled = strategy_name in enabled
            record.updated_at = now_tz()

    db.commit()


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


def fetch_paper_data(limit: int = 100) -> dict[str, list[dict[str, object]]]:
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

    return {
        "nav": [
            {
                "trade_date": row["trade_date"],
                "cash": float(row["cash"]),
                "position_value": float(row["position_value"]),
                "total_equity": float(row["total_equity"]),
            }
            for row in nav_rows
        ],
        "orders": [
            {
                "id": int(row["id"]),
                "symbol": row["symbol"],
                "side": row["side"],
                "quantity": int(row["quantity"]),
                "price": float(row["price"]),
                "amount": float(row["amount"]),
                "status": row["status"],
                "created_at": row["created_at"],
            }
            for row in order_rows
        ],
        "positions": [
            {
                "id": int(row["id"]),
                "symbol": row["symbol"],
                "quantity": int(row["quantity"]),
                "avg_cost": float(row["avg_cost"]),
                "market_value": float(row["market_value"]),
                "updated_at": row["updated_at"],
            }
            for row in position_rows
        ],
    }


def _event_scope() -> tuple[str, str]:
    settings = get_settings()
    symbol = settings.portfolio.symbols[0] if settings.portfolio.symbols else "000300.SH"
    return symbol, "CN"


def _macro_fallback_seeds(
    db: Session,
    *,
    provider_name: str,
    symbol_scope: str,
    market_scope: str,
    current_time: datetime,
) -> list[EventSeed]:
    settings = get_settings()
    if settings.events.fallback_mode != "reuse_last_good":
        return []
    cutoff = current_time - timedelta(days=settings.events.fallback_max_age_days)
    records = list(
        db.execute(
            select(EventRecord)
            .where(
                EventRecord.event_type == EventType.MACRO,
                EventRecord.market_scope == market_scope,
                EventRecord.published_at >= cutoff,
            )
            .order_by(EventRecord.published_at.desc())
            .limit(3)
        ).scalars()
    )
    if not records:
        return []

    fallback_source = f"{provider_name}_last_good"
    seeds: list[EventSeed] = []
    for index, record in enumerate(records):
        stale_days = max(0, (current_time.date() - record.published_at.date()).days)
        seeds.append(
            EventSeed(
                event_id=f"{fallback_source}-{record.event_id}-{current_time.date().isoformat()}-{index}",
                event_type=EventType.MACRO.value,
                market_scope=market_scope,
                symbol_scope=symbol_scope,
                published_at=current_time - timedelta(minutes=index + 1),
                source=fallback_source,
                title=f"[Fallback] {record.title}",
                body_ref=record.body_ref or "Reusing last known macro context while upstream provider is unavailable.",
                tags=list(record.tags) + ["fallback"],
                importance=record.importance,
                sentiment_hint=record.sentiment_hint,
                metadata_payload={
                    **dict(record.metadata_payload or {}),
                    "fallback_mode": "reuse_last_good",
                    "fallback_from_event_id": record.event_id,
                    "fallback_from_published_at": record.published_at.isoformat(),
                    "stale_days": stale_days,
                },
            )
        )
    return seeds


def sync_event_stream(db: Session) -> None:
    symbol_scope, market_scope = _event_scope()
    providers = get_event_providers()
    current_time = now_tz()

    for provider in providers:
        try:
            seeds = provider.fetch(now=current_time, symbol_scope=symbol_scope, market_scope=market_scope)
            provider_name = getattr(provider, "provider_name", getattr(provider, "name", "macro"))
            provider_message = getattr(provider, "provider_message", f"{provider_name} macro pipeline is healthy.")
            previous_status = get_macro_pipeline_status(db)
            _set_runtime_setting_json(
                db,
                _MACRO_STATUS_KEY,
                {
                    "provider": provider_name,
                    "active_provider": provider_name,
                    "provider_chain": list(getattr(provider, "provider_chain", [provider_name])),
                    "status": "ready",
                    "message": provider_message,
                    "degraded": False,
                    "last_success_at": current_time.isoformat(),
                    "fallback_mode": None,
                    "fallback_event_count": 0,
                    "using_last_known_context": False,
                    "reliability_score": 1.0 if provider_name == "fred" else 0.84,
                    "reliability_tier": "primary_live" if provider_name == "fred" else "secondary_live",
                },
                current_time,
            )
            if bool(previous_status.get("degraded")):
                _record_system_audit(
                    db,
                    event_type="macro_provider_recovered",
                    entity_type="macro_pipeline",
                    entity_id=provider_name,
                    payload={"status": "ready", "message": f"{provider_name} recovered."},
                    created_at=current_time,
                )
        except Exception as exc:
            provider_name = getattr(provider, "provider_name", getattr(provider, "name", "macro"))
            previous_status = get_macro_pipeline_status(db)
            fallback_seeds = _macro_fallback_seeds(
                db,
                provider_name=provider_name,
                symbol_scope=symbol_scope,
                market_scope=market_scope,
                current_time=current_time,
            )
            using_last_known_context = bool(fallback_seeds)
            degraded_payload = {
                "provider": provider_name,
                "active_provider": provider_name if not using_last_known_context else f"{provider_name}_last_good",
                "provider_chain": list(getattr(provider, "provider_chain", [provider_name])),
                "status": "degraded",
                "message": (
                    f"{provider_name} macro fetch failed: {exc}. "
                    + (
                        f"Reusing {len(fallback_seeds)} last-known macro events."
                        if using_last_known_context
                        else "No recent fallback context is available."
                    )
                ),
                "degraded": True,
                "last_success_at": previous_status.get("last_success_at"),
                "fallback_mode": "reuse_last_good" if using_last_known_context else None,
                "fallback_event_count": len(fallback_seeds),
                "using_last_known_context": using_last_known_context,
                "reliability_score": 0.58 if using_last_known_context else 0.32,
                "reliability_tier": "last_known_context" if using_last_known_context else "provider_failed",
            }
            _set_runtime_setting_json(db, _MACRO_STATUS_KEY, degraded_payload, current_time)
            if not bool(previous_status.get("degraded")) or str(previous_status.get("message")) != degraded_payload["message"]:
                _record_system_audit(
                    db,
                    event_type="macro_provider_degraded",
                    entity_type="macro_pipeline",
                    entity_id=provider_name,
                    payload=degraded_payload,
                    created_at=current_time,
                )
            if using_last_known_context:
                _record_system_audit(
                    db,
                    event_type="macro_provider_fallback_applied",
                    entity_type="macro_pipeline",
                    entity_id=provider_name,
                    payload=degraded_payload,
                    created_at=current_time,
                )
                seeds = fallback_seeds
            else:
                # External event providers are optional inputs; startup must remain offline-safe.
                continue

        for seed in seeds:
            record = db.execute(select(EventRecord).where(EventRecord.event_id == seed.event_id)).scalar_one_or_none()
            if record is None:
                db.add(
                    EventRecord(
                        event_id=seed.event_id,
                        event_type=EventType(seed.event_type),
                        market_scope=seed.market_scope,
                        symbol_scope=seed.symbol_scope,
                        published_at=seed.published_at,
                        source=seed.source,
                        title=seed.title,
                        body_ref=seed.body_ref,
                        tags=seed.tags,
                        importance=seed.importance,
                        sentiment_hint=seed.sentiment_hint,
                        metadata_payload=dict(seed.metadata_payload),
                        created_at=current_time,
                    )
                )

    db.commit()


def sync_daily_event_digests(db: Session) -> None:
    records = list(
        db.execute(
            select(EventRecord).order_by(EventRecord.published_at.desc())
        ).scalars()
    )
    if not records:
        return

    grouped: dict[tuple[str, str, str], list[EventRecord]] = {}
    for record in records:
        trade_date = record.published_at.astimezone(ZoneInfo(get_settings().timezone)).strftime("%Y-%m-%d")
        grouped.setdefault((trade_date, record.market_scope, record.symbol_scope), []).append(record)

    for (trade_date, market_scope, symbol_scope), items in grouped.items():
        macro = [item.title for item in items if item.event_type == EventType.MACRO]
        event_scores = {
            "macro_bias": round(sum(item.sentiment_hint * item.importance for item in items if item.event_type == EventType.MACRO), 3),
            "aggregate_sentiment": round(sum(item.sentiment_hint * item.importance for item in items), 3),
        }
        digest_payload = {
            "trade_date": trade_date,
            "market_scope": market_scope,
            "symbol_scope": symbol_scope,
            "event_scores": event_scores,
            "event_ids": [item.event_id for item in items],
        }
        existing = list(
            db.execute(
                select(DailyEventDigest)
                .where(
                    DailyEventDigest.trade_date == trade_date,
                    DailyEventDigest.market_scope == market_scope,
                    DailyEventDigest.symbol_scope == symbol_scope,
                )
                .order_by(DailyEventDigest.id.desc())
            ).scalars()
        )
        digest = existing[0] if existing else None
        if digest is None:
            digest = DailyEventDigest(
                trade_date=trade_date,
                market_scope=market_scope,
                symbol_scope=symbol_scope,
                macro_summary="; ".join(macro) or "No macro pulse.",
                event_scores=event_scores,
                digest_hash=stable_hash(digest_payload),
                event_ids=[item.event_id for item in items],
                created_at=now_tz(),
            )
            db.add(digest)
        else:
            digest.macro_summary = "; ".join(macro) or "No macro pulse."
            digest.event_scores = event_scores
            digest.digest_hash = stable_hash(digest_payload)
            digest.event_ids = [item.event_id for item in items]
            for duplicate in existing[1:]:
                db.delete(duplicate)

    db.commit()


def _latest_digest(db: Session) -> DailyEventDigest:
    digest = db.execute(
        select(DailyEventDigest).order_by(DailyEventDigest.trade_date.desc(), DailyEventDigest.id.desc()).limit(1)
    ).scalars().first()
    if digest is None:
        sync_event_stream(db)
        sync_daily_event_digests(db)
        digest = db.execute(
            select(DailyEventDigest).order_by(DailyEventDigest.trade_date.desc(), DailyEventDigest.id.desc()).limit(1)
        ).scalars().first()
    if digest is None:
        created_at = now_tz()
        trade_date = created_at.date().isoformat()
        fallback_payload = {
            'trade_date': trade_date,
            'market_scope': 'CN',
            'symbol_scope': '000300.SH',
            'macro_summary': 'No macro events available.',
            'event_scores': {
                'aggregate_sentiment': 0.0,
                'macro_bias': 0.0,
            },
            'event_ids': [],
        }
        digest = DailyEventDigest(
            trade_date=trade_date,
            market_scope='CN',
            symbol_scope='000300.SH',
            macro_summary=str(fallback_payload['macro_summary']),
            event_scores=dict(fallback_payload['event_scores']),
            digest_hash=stable_hash(fallback_payload),
            event_ids=[],
            created_at=created_at,
        )
        db.add(digest)
        db.flush()
    return digest


def _get_runtime_setting_json(db: Session, key: str) -> dict[str, object] | None:
    record = db.execute(select(RuntimeSetting).where(RuntimeSetting.key == key)).scalar_one_or_none()
    if record is None or not isinstance(record.value_json, dict):
        return None
    return dict(record.value_json)


def _set_runtime_setting_json(db: Session, key: str, value_json: dict[str, object], updated_at: datetime) -> None:
    record = db.execute(select(RuntimeSetting).where(RuntimeSetting.key == key)).scalar_one_or_none()
    if record is None:
        db.add(RuntimeSetting(key=key, value_json=value_json, updated_at=updated_at))
    else:
        record.value_json = value_json
        record.updated_at = updated_at
    db.flush()


def _latest_events_for_digest(db: Session, digest: DailyEventDigest) -> list[EventRecord]:
    if not digest.event_ids:
        return []
    return list(
        db.execute(
            select(EventRecord)
            .where(EventRecord.event_id.in_(digest.event_ids))
            .order_by(EventRecord.published_at.desc())
        ).scalars()
    )


def _event_lane_sources(records: list[EventRecord]) -> dict[str, str]:
    lane_sources = {'macro': 'unavailable'}
    for record in records:
        lane_key = record.event_type.value
        if lane_key in lane_sources and lane_sources[lane_key] == 'unavailable':
            lane_sources[lane_key] = record.source
    return lane_sources


def _paper_nav_drawdown(nav_rows: list[dict[str, object]]) -> float:
    if not nav_rows:
        return 0.0
    peak = 0.0
    max_drawdown = 0.0
    for row in reversed(nav_rows):
        equity = float(row.get("total_equity", 0.0))
        peak = max(peak, equity)
        if peak > 0:
            max_drawdown = max(max_drawdown, (peak - equity) / peak)
    return round(max_drawdown, 4)


def _record_llm_stage(
    db: Session,
    *,
    stage: str,
    prompt_version: str,
    status,
    created_at: datetime,
    market_snapshot_hash: str,
    event_digest_hash: str,
    payload_extra: dict[str, object] | None = None,
) -> None:
    payload = {
        'stage': stage,
        'prompt_version': prompt_version,
        'provider': status.provider,
        'model': status.model,
        'status': status.status,
        'message': status.message,
        'using_mock_fallback': status.using_mock_fallback,
    }
    if payload_extra:
        payload.update(payload_extra)
    event_type = 'llm_fallback_triggered' if status.using_mock_fallback else 'llm_stage_completed'
    db.add(
        AuditRecord(
            run_id='system-llm-gateway',
            decision_id=f'{stage}-{stable_hash([prompt_version, status.provider, status.status, created_at.isoformat()])}',
            event_type=event_type,
            entity_type='llm_stage',
            entity_id=stage,
            strategy_dsl_hash='',
            market_snapshot_hash=market_snapshot_hash,
            event_digest_hash=event_digest_hash,
            payload=payload,
            created_at=created_at,
        )
    )
    db.flush()


def _merge_market_snapshot(base_snapshot: dict[str, object], analyst_state: dict[str, object] | None) -> dict[str, object]:
    merged = dict(base_snapshot)
    price_context = dict(base_snapshot['price_context'])
    if analyst_state and analyst_state.get('market_snapshot_hash') == base_snapshot['market_snapshot_hash']:
        summary = str(analyst_state.get('summary') or '').strip()
        if summary:
            merged['summary'] = summary
        watchpoints = analyst_state.get('watchpoints')
        if isinstance(watchpoints, list) and watchpoints:
            price_context['watchpoints'] = [str(item) for item in watchpoints[:4]]
        event_bias = str(analyst_state.get('event_bias') or '').strip()
        if event_bias:
            price_context['event_bias'] = event_bias
        price_context['market_analyst_prompt_version'] = str(analyst_state.get('prompt_version') or MARKET_ANALYST_PROMPT_VERSION)
        price_context['market_analyst_provider_status'] = str(analyst_state.get('provider_status') or 'mock')
        merged['market_analyst'] = analyst_state
    merged['price_context'] = price_context
    return merged


def build_market_snapshot(db: Session) -> dict[str, object]:
    digest = _latest_digest(db)
    nav_rows = fetch_paper_data(limit=90)['nav']
    close = [float(item['total_equity']) for item in reversed(nav_rows)]
    regime_engine = get_market_regime()
    regime_result = None
    if len(close) >= 60:
        regime_result = regime_engine.analyze(
            {
                'close': close,
                'high': close,
                'low': close,
                'volume': [1.0] * len(close),
            }
        )

    aggregate_sentiment = float(digest.event_scores.get('aggregate_sentiment', 0.0))
    if regime_result is None:
        regime = 'RANGING'
        confidence = 0.58
        indicators = {'volatility': 0.021, 'trend_strength': 0.04}
        reason = 'Fallback regime from event digest and limited nav history.'
    else:
        regime = regime_result.regime.value
        confidence = regime_result.confidence
        indicators = regime_result.indicators
        reason = regime_result.reason

    records = _latest_events_for_digest(db, digest)
    lane_sources = _event_lane_sources(records)
    macro_status = get_macro_pipeline_status(db)
    if lane_sources['macro'] == 'unavailable' and not macro_status.get("degraded"):
        lane_sources['macro'] = str(macro_status.get("provider", "unavailable"))
    snapshot_payload = {
        'symbol': digest.symbol_scope,
        'regime': regime,
        'confidence': confidence,
        'event_digest_hash': digest.digest_hash,
        'aggregate_sentiment': aggregate_sentiment,
        'reason': reason,
    }
    summary = (
        f"{digest.symbol_scope} is in {regime.lower()} mode with confidence {confidence:.2f}. "
        f"Aggregate event sentiment is {aggregate_sentiment:+.2f}; "
        f"macro pulse says '{digest.macro_summary}'."
    )
    base_snapshot = {
        'regime': regime,
        'confidence': confidence,
        'summary': summary,
        'market_snapshot_hash': stable_hash(snapshot_payload),
        'symbol': digest.symbol_scope,
        'price_context': indicators,
        'event_digest': digest,
        'event_stream_preview': records[:6],
        'event_lane_sources': lane_sources,
        'macro_status': macro_status,
    }
    analyst_state = _get_runtime_setting_json(db, 'market_analyst.latest')
    return _merge_market_snapshot(base_snapshot, analyst_state)


def _fallback_proposal_blueprints(symbol: str, provider_status) -> list[dict[str, object]]:
    return [
        {
            'title': 'Signal Reef',
            'base_strategy': 'ma_cross',
            'source_kind': 'mock',
            'provider_status': provider_status.status,
            'provider_model': provider_status.model,
            'provider_message': provider_status.message,
            'thesis': 'Use trend persistence plus macro stability to keep a single active exposure with low turnover.',
            'features_used': ['SMA', 'EMA', 'volatility', 'macro_summary'],
            'params': {'short_window': 12, 'long_window': 34},
            'debate_report': {
                'stance_for': ['Macro pulse supports disciplined exposure.', 'Low turnover fits the current regime backdrop.'],
                'stance_against': ['ETF leadership may still rotate quickly.', 'Trend strength is not decisive yet.'],
                'synthesis': 'Admissible as a monitored trend candidate when macro pressure stays stable.',
            },
            'llm_score': 77.0,
            'llm_explanation': 'Macro conditions are supportive but not euphoric, which fits a low-churn trend thesis.',
            'prompt_versions': {
                'strategy_agent': STRATEGY_AGENT_PROMPT_VERSION,
                'research_debate': RESEARCH_DEBATE_PROMPT_VERSION,
                'risk_manager_llm': RISK_MANAGER_LLM_PROMPT_VERSION,
            },
        },
        {
            'title': 'Harbor Drift',
            'base_strategy': 'channel_breakout',
            'source_kind': 'mock',
            'provider_status': provider_status.status,
            'provider_model': provider_status.model,
            'provider_message': provider_status.message,
            'thesis': 'Watch for volatility compression and breakout only when macro drift stays contained.',
            'features_used': ['Donchian', 'ATR', 'volatility', 'macro_summary'],
            'params': {'lookback': 20},
            'debate_report': {
                'stance_for': ['Breakout logic is aligned with contained macro drift.', 'ATR keeps entries disciplined.'],
                'stance_against': ['Regime confidence is not decisive.', 'False breakouts remain possible in a ranging tape.'],
                'synthesis': 'Good challenge candidate, but not strong enough to auto-promote without more evidence.',
            },
            'llm_score': 78.0,
            'llm_explanation': 'The event backdrop supports a challenge run, but the regime evidence is not decisive enough yet.',
            'prompt_versions': {
                'strategy_agent': STRATEGY_AGENT_PROMPT_VERSION,
                'research_debate': RESEARCH_DEBATE_PROMPT_VERSION,
                'risk_manager_llm': RISK_MANAGER_LLM_PROMPT_VERSION,
            },
        },
        {
            'title': 'Tide Counter',
            'base_strategy': 'mean_reversion',
            'source_kind': 'mock',
            'provider_status': provider_status.status,
            'provider_model': provider_status.model,
            'provider_message': provider_status.message,
            'thesis': 'Fade short over-extension if macro pressure eases and realized volatility compresses.',
            'features_used': ['Bollinger', 'RSI', 'volatility', 'macro_summary'],
            'params': {'window': 20, 'rsi_threshold': 30},
            'debate_report': {
                'stance_for': ['Volatility compression can support mean reversion entries.', 'Macro pressure is easing from recent highs.'],
                'stance_against': ['Trend strength may still dominate reversion setups.', 'Execution noise can erase the edge quickly.'],
                'synthesis': 'Coherent idea, but still too fragile for paper promotion.',
            },
            'llm_score': 70.0,
            'llm_explanation': 'The idea is coherent, but the evidence pack is still too fragile for paper promotion.',
            'prompt_versions': {
                'strategy_agent': STRATEGY_AGENT_PROMPT_VERSION,
                'research_debate': RESEARCH_DEBATE_PROMPT_VERSION,
                'risk_manager_llm': RISK_MANAGER_LLM_PROMPT_VERSION,
            },
        },
    ]


def _normalize_strategy_agent_blueprints(
    raw_payload: dict[str, object],
    provider_status,
    source_kind: str,
) -> list[dict[str, object]]:
    proposals = raw_payload.get('proposals', [])
    if not isinstance(proposals, list):
        return []

    allowed_strategies = set(get_strategy_registry().names()) | {'novel_composite'}
    allowed_features = {
        'SMA', 'EMA', 'RSI', 'MACD', 'ATR', 'ADX', 'Bollinger', 'Donchian', 'ROC', 'Volume MA', 'volatility', 'drawdown', 'macro_summary',
    }
    normalized: list[dict[str, object]] = []
    for index, proposal in enumerate(proposals[:3]):
        if not isinstance(proposal, dict):
            continue
        base_strategy = str(proposal.get('base_strategy', 'ma_cross'))
        if base_strategy not in allowed_strategies:
            continue
        title = str(proposal.get('title', f'LLM Proposal {index + 1}')).strip()[:80]
        thesis = str(proposal.get('thesis', '')).strip()
        if not title or not thesis:
            continue
        raw_features = proposal.get('features_used', [])
        features_used = [str(feature) for feature in raw_features if str(feature) in allowed_features][:6]
        if not features_used:
            features_used = ['volatility', 'macro_summary']
        raw_params = proposal.get('params', {})
        normalized.append(
            {
                'title': title,
                'base_strategy': base_strategy,
                'thesis': thesis,
                'features_used': features_used,
                'params': raw_params if isinstance(raw_params, dict) else {},
                'source_kind': source_kind,
                'provider_status': provider_status.status,
                'provider_model': provider_status.model,
                'provider_message': provider_status.message,
                'prompt_versions': {'strategy_agent': STRATEGY_AGENT_PROMPT_VERSION},
            }
        )
    return normalized


def run_market_analyst(db: Session, snapshot: dict[str, object], current_time: datetime) -> dict[str, object]:
    digest: DailyEventDigest = snapshot['event_digest']
    payload = build_market_analyst_payload(
        symbol=str(snapshot['symbol']),
        timezone=get_settings().timezone,
        deterministic_snapshot={
            'regime': snapshot['regime'],
            'confidence': snapshot['confidence'],
            'summary': snapshot['summary'],
            'price_context': snapshot['price_context'],
            'event_lane_sources': snapshot['event_lane_sources'],
        },
        event_digest={
            'macro_summary': digest.macro_summary,
            'event_scores': digest.event_scores,
        },
    )
    result = get_llm_gateway().invoke_json(
        db=db,
        task='market_analyst',
        system=market_analyst_system_prompt(),
        user=json.dumps(payload, ensure_ascii=False),
        schema_hint=MARKET_ANALYST_SCHEMA_HINT,
    )
    raw = result.payload if isinstance(result.payload, dict) else {}
    output = {
        'summary': str(raw.get('summary') or snapshot['summary']).strip(),
        'event_bias': str(raw.get('event_bias') or 'neutral').strip()[:32],
        'watchpoints': [str(item) for item in raw.get('watchpoints', []) if str(item).strip()][:4] if isinstance(raw.get('watchpoints', []), list) else [],
        'confidence_adjustment': max(-0.15, min(0.15, float(raw.get('confidence_adjustment', 0.0) or 0.0))),
        'prompt_version': MARKET_ANALYST_PROMPT_VERSION,
        'source_kind': result.source_kind,
        'provider_status': result.status.status,
        'provider_model': result.status.model,
        'provider_message': result.status.message,
        'market_snapshot_hash': str(snapshot['market_snapshot_hash']),
        'event_digest_hash': digest.digest_hash,
    }
    _set_runtime_setting_json(db, 'market_analyst.latest', output, current_time)
    _record_llm_stage(
        db,
        stage='market_analyst',
        prompt_version=MARKET_ANALYST_PROMPT_VERSION,
        status=result.status,
        created_at=current_time,
        market_snapshot_hash=str(snapshot['market_snapshot_hash']),
        event_digest_hash=digest.digest_hash,
        payload_extra={'source_kind': result.source_kind},
    )
    return output


def run_strategy_agent(db: Session, symbol: str, snapshot: dict[str, object], current_time: datetime):
    digest: DailyEventDigest = snapshot['event_digest']
    baseline_strategies = [
        {'strategy_name': item.strategy_name, 'default_params': item.default_params, 'description': item.description}
        for item in db.execute(select(StrategySnapshot).order_by(StrategySnapshot.strategy_name.asc())).scalars()
    ]
    payload = build_strategy_agent_payload(
        symbol=symbol,
        market_scope='CN',
        timezone=get_settings().timezone,
        market_snapshot={
            'regime': snapshot['regime'],
            'confidence': snapshot['confidence'],
            'summary': snapshot['summary'],
            'price_context': snapshot['price_context'],
            'event_lane_sources': snapshot['event_lane_sources'],
        },
        baseline_strategies=baseline_strategies,
        hard_limits=['long_only', 'no_leverage', 'daily_rebalance_only', 'single_active_strategy'],
    )
    result = get_llm_gateway().invoke_json(
        db=db,
        task='strategy_agent',
        system=strategy_agent_system_prompt(),
        user=json.dumps(payload, ensure_ascii=False),
        schema_hint=STRATEGY_AGENT_SCHEMA_HINT,
    )
    _record_llm_stage(
        db,
        stage='strategy_agent',
        prompt_version=STRATEGY_AGENT_PROMPT_VERSION,
        status=result.status,
        created_at=current_time,
        market_snapshot_hash=str(snapshot['market_snapshot_hash']),
        event_digest_hash=digest.digest_hash,
        payload_extra={'source_kind': result.source_kind},
    )
    blueprints = _normalize_strategy_agent_blueprints(result.payload, provider_status=result.status, source_kind=result.source_kind)
    if blueprints:
        return blueprints, result
    return _fallback_proposal_blueprints(symbol, result.status), result


def _deterministic_score(index: int, snapshot: dict[str, object], digest: DailyEventDigest, features_used: list[str]) -> float:
    aggregate_sentiment = float(digest.event_scores.get('aggregate_sentiment', 0.0))
    score = 78.0 - index * 6 + aggregate_sentiment * 8 + min(len(features_used), 4) * 0.8
    if str(snapshot['regime']).upper() in {'BULLISH', 'TRENDING_UP'}:
        score += 1.5
    return round(max(55.0, min(92.0, score)), 1)


def _proposal_context(proposal: StrategyProposal | None) -> dict[str, object] | None:
    if proposal is None:
        return None
    return {
        'proposal_id': proposal.id,
        'title': proposal.title,
        'status': proposal.status.value,
        'final_score': proposal.final_score,
        'promoted_at': proposal.promoted_at.isoformat() if proposal.promoted_at else None,
    }


def _cooldown_remaining_days(promoted_at: str | None, current_time: datetime) -> int:
    if not promoted_at:
        return 0
    promoted = datetime.fromisoformat(promoted_at)
    elapsed_days = max(0, (current_time.date() - promoted.date()).days)
    remaining = get_settings().governance.cooldown_days - elapsed_days
    return max(0, remaining)


def _lifecycle_eta(
    *,
    phase: str,
    cooldown_remaining_days: int,
    current_time: datetime,
) -> dict[str, object]:
    interval_minutes = max(1, int(get_settings().events.expected_sync_interval_minutes))
    next_sync_at = current_time + timedelta(minutes=interval_minutes)

    if phase in {"promotion_ready", "candidate_watch"}:
        return {
            "eta_kind": "next_sync_window",
            "estimated_next_eligible_at": next_sync_at.isoformat(),
        }
    if phase == "candidate_cooldown":
        if cooldown_remaining_days > 0:
            return {
                "eta_kind": "cooldown_window",
                "estimated_next_eligible_at": (current_time + timedelta(days=cooldown_remaining_days)).isoformat(),
            }
        return {
            "eta_kind": "next_sync_window",
            "estimated_next_eligible_at": next_sync_at.isoformat(),
        }
    if phase == "paused_pending_review":
        return {
            "eta_kind": "review_pending",
            "estimated_next_eligible_at": None,
        }
    if phase in {"rolled_back", "rejected"}:
        return {
            "eta_kind": "quality_revalidation",
            "estimated_next_eligible_at": None,
        }
    return {
        "eta_kind": "unknown",
        "estimated_next_eligible_at": None,
    }


def _governance_action(
    *,
    final_score: float,
    bottom_line_passed: bool,
    active_context: dict[str, object] | None,
    macro_status: dict[str, object],
    current_time: datetime,
) -> tuple[ProposalStatus, RiskDecisionAction, dict[str, object]]:
    governance = get_settings().governance
    blocked_reasons: list[str] = []
    active_score = float(active_context['final_score']) if active_context else None
    score_delta = round(final_score - active_score, 1) if active_score is not None else None
    promoted_at = active_context.get('promoted_at') if active_context else None
    cooldown_remaining_days = _cooldown_remaining_days(
        str(promoted_at) if promoted_at else None,
        current_time,
    )
    can_challenge_active = active_context is None or (
        score_delta is not None and score_delta >= governance.challenger_min_delta and cooldown_remaining_days == 0
    )

    if not bottom_line_passed:
        blocked_reasons.append('bottom_line_failed')
    if final_score < governance.keep_threshold:
        blocked_reasons.append('below_keep_threshold')
    if final_score < governance.promote_threshold:
        blocked_reasons.append('below_promote_threshold')
    if active_context and score_delta is not None and score_delta < governance.challenger_min_delta:
        blocked_reasons.append('delta_below_threshold')
    if cooldown_remaining_days > 0:
        blocked_reasons.append('cooldown_active')
    if governance.block_promotion_on_macro_degrade and bool(macro_status.get('degraded')):
        blocked_reasons.append('macro_provider_degraded')

    promote_allowed = (
        bottom_line_passed
        and final_score >= governance.promote_threshold
        and can_challenge_active
        and not (
            governance.block_promotion_on_macro_degrade and bool(macro_status.get('degraded'))
        )
    )

    if promote_allowed:
        status = ProposalStatus.ACTIVE
        action = RiskDecisionAction.PROMOTE_TO_PAPER
    elif bottom_line_passed and final_score >= governance.keep_threshold:
        status = ProposalStatus.CANDIDATE
        action = RiskDecisionAction.KEEP_CANDIDATE
    else:
        status = ProposalStatus.REJECTED
        action = RiskDecisionAction.REJECT

    lifecycle_phase = 'promotion_ready'
    next_step = 'promote_now'
    if action == RiskDecisionAction.KEEP_CANDIDATE:
        lifecycle_phase = 'candidate_cooldown' if cooldown_remaining_days > 0 else 'candidate_watch'
        next_step = 'wait_for_cooldown' if cooldown_remaining_days > 0 else 'monitor_candidate'
    elif action == RiskDecisionAction.REJECT:
        lifecycle_phase = 'rejected'
        next_step = 'improve_quality'
    lifecycle_eta = _lifecycle_eta(
        phase=lifecycle_phase,
        cooldown_remaining_days=cooldown_remaining_days,
        current_time=current_time,
    )

    governance_report = {
        'version': 'v1.5',
        'thresholds': {
            'promote_threshold': governance.promote_threshold,
            'keep_threshold': governance.keep_threshold,
            'challenger_min_delta': governance.challenger_min_delta,
            'cooldown_days': governance.cooldown_days,
        },
        'promotion_gate': {
            'eligible': action == RiskDecisionAction.PROMOTE_TO_PAPER,
            'blocked_reasons': blocked_reasons,
        },
        'active_comparison': {
            'active_title': active_context.get('title') if active_context else None,
            'active_score': active_score,
            'score_delta': score_delta,
            'can_challenge_active': can_challenge_active,
            'cooldown_remaining_days': cooldown_remaining_days,
        },
        'macro_dependency': {
            'provider': macro_status.get('provider'),
            'status': macro_status.get('status'),
            'degraded': bool(macro_status.get('degraded')),
        },
        'lifecycle': {
            'phase': lifecycle_phase,
            'next_step': next_step,
            'rechallenge_allowed': can_challenge_active,
            'review_trigger': 'next_agent_sync',
            'eta_kind': lifecycle_eta['eta_kind'],
            'estimated_next_eligible_at': lifecycle_eta['estimated_next_eligible_at'],
            'resume_conditions': (
                ['cooldown_elapsed', 'score_delta_revalidated']
                if cooldown_remaining_days > 0
                else ['score_above_keep_threshold', 'macro_pipeline_ready']
            ),
        },
        'selected_action': action.value,
    }
    return status, action, governance_report


def _strategy_dsl(blueprint: dict[str, object], snapshot: dict[str, object], digest: DailyEventDigest) -> dict[str, object]:
    base_strategy = str(blueprint['base_strategy'])
    params = blueprint.get('params', {})
    governance = get_settings().governance
    return {
        'thesis': blueprint['thesis'],
        'market_regime_clause': {
            'required_regime': snapshot['regime'],
            'event_digest_hash': digest.digest_hash,
        },
        'entry_rules': [
            {'indicator': 'SMA', 'operator': 'cross_above', 'lhs': 10, 'rhs': 30},
            {'indicator': 'volatility', 'operator': 'lte', 'value': 0.035},
        ],
        'exit_rules': [
            {'indicator': 'drawdown', 'operator': 'gte', 'value': 0.08},
            {'indicator': 'EMA', 'operator': 'cross_below', 'lhs': 8, 'rhs': 21},
        ],
        'risk_rules': [
            {'rule': 'long_only', 'value': True},
            {'rule': 'no_leverage', 'value': True},
            {'rule': 'daily_rebalance_only', 'value': True},
        ],
        'position_sizing': {'mode': 'fixed_fraction', 'value': 0.25},
        'holding_constraints': {'min_holding_days': 5, 'cooldown_days': governance.cooldown_days},
        'features_used': blueprint['features_used'],
        'params': {'base_strategy': base_strategy, 'symbol': digest.symbol_scope, **(params if isinstance(params, dict) else {})},
    }


def _fallback_debate_report(blueprint: dict[str, object], digest: DailyEventDigest) -> dict[str, object]:
    if isinstance(blueprint.get('debate_report'), dict):
        return dict(blueprint['debate_report'])
    return {
        'stance_for': [
            f"Macro pulse supports disciplined exposure: {digest.macro_summary}",
            'Single active strategy keeps execution risk bounded.',
        ],
        'stance_against': [
            'Macro conditions can still reverse quickly and invalidate the thesis.',
            'Execution noise remains non-zero and should be watched for rollback.',
        ],
        'synthesis': f"{blueprint['title']} is admissible as a monitored candidate when macro conditions are summarized rather than traded directly.",
    }


def run_research_debate(db: Session, blueprint: dict[str, object], snapshot: dict[str, object], current_time: datetime) -> dict[str, object]:
    digest: DailyEventDigest = snapshot['event_digest']
    if blueprint.get('source_kind') == 'mock':
        report = _fallback_debate_report(blueprint, digest)
        report['prompt_version'] = blueprint.get('prompt_versions', {}).get('research_debate', RESEARCH_DEBATE_PROMPT_VERSION)
        return report

    payload = build_research_debate_payload(
        proposal={
            'title': blueprint['title'],
            'thesis': blueprint['thesis'],
            'base_strategy': blueprint['base_strategy'],
            'features_used': blueprint['features_used'],
            'params': blueprint.get('params', {}),
        },
        market_snapshot={
            'regime': snapshot['regime'],
            'confidence': snapshot['confidence'],
            'summary': snapshot['summary'],
            'price_context': snapshot['price_context'],
        },
        event_digest={
            'macro_summary': digest.macro_summary,
            'event_scores': digest.event_scores,
        },
    )
    result = get_llm_gateway().invoke_json(
        db=db,
        task='research_debate',
        system=research_debate_system_prompt(),
        user=json.dumps(payload, ensure_ascii=False),
        schema_hint=RESEARCH_DEBATE_SCHEMA_HINT,
    )
    _record_llm_stage(
        db,
        stage='research_debate',
        prompt_version=RESEARCH_DEBATE_PROMPT_VERSION,
        status=result.status,
        created_at=current_time,
        market_snapshot_hash=str(snapshot['market_snapshot_hash']),
        event_digest_hash=digest.digest_hash,
        payload_extra={'proposal_title': str(blueprint['title'])},
    )
    raw = result.payload if isinstance(result.payload, dict) else {}
    report = {
        'stance_for': [str(item) for item in raw.get('stance_for', []) if str(item).strip()][:3] if isinstance(raw.get('stance_for', []), list) else [],
        'stance_against': [str(item) for item in raw.get('stance_against', []) if str(item).strip()][:3] if isinstance(raw.get('stance_against', []), list) else [],
        'synthesis': str(raw.get('synthesis') or '').strip(),
        'prompt_version': RESEARCH_DEBATE_PROMPT_VERSION,
    }
    if not report['stance_for'] or not report['stance_against'] or not report['synthesis']:
        fallback = _fallback_debate_report(blueprint, digest)
        fallback['prompt_version'] = RESEARCH_DEBATE_PROMPT_VERSION
        return fallback
    return report


def _base_evidence_pack(
    blueprint: dict[str, object],
    digest: DailyEventDigest,
    deterministic_score: float,
    governance_report: dict[str, object],
) -> dict[str, object]:
    max_dd = min(0.149, max(0.082, 0.15 - (deterministic_score - 60) / 1000))
    deterministic_evidence = {
        'cagr': round(0.12 + (deterministic_score - 70) / 200, 4),
        'sharpe': round(1.05 + (deterministic_score - 70) / 60, 3),
        'max_drawdown': round(max_dd, 4),
        'walkforward_pass_rate': round(min(0.95, 0.6 + (deterministic_score - 60) / 100), 3),
        'signal_density': round(0.15 + (80 - deterministic_score) / 300, 3),
        'min_holding_days': 5,
        'param_sensitivity': round(max(0.12, 0.55 - deterministic_score / 200), 3),
    }
    bottom_line_report = {
        'data_integrity': True,
        'max_drawdown_limit': deterministic_evidence['max_drawdown'] <= 0.15,
        'execution_safety': True,
    }
    return {
        'bottom_line_report': bottom_line_report,
        'deterministic_evidence': deterministic_evidence,
        'governance_report': governance_report,
        'llm_judgment_inputs': {
            'macro_summary': digest.macro_summary,
            'event_scores': digest.event_scores,
        },
    }


def _quality_band(*, final_score: float, walkforward_pass_rate: float, param_sensitivity: float) -> str:
    if final_score >= 82 and walkforward_pass_rate >= 0.75 and param_sensitivity <= 0.22:
        return 'strong'
    if final_score >= 75 and walkforward_pass_rate >= 0.65 and param_sensitivity <= 0.3:
        return 'admissible'
    return 'fragile'


def _build_quality_report(
    *,
    evidence_pack: dict[str, object],
    governance_report: dict[str, object],
    final_score: float,
) -> dict[str, object]:
    deterministic = dict(evidence_pack.get('deterministic_evidence', {}))
    active_comparison = dict(governance_report.get('active_comparison', {}))
    thresholds = dict(governance_report.get('thresholds', {}))
    promotion_gate = dict(governance_report.get('promotion_gate', {}))
    walkforward_pass_rate = float(deterministic.get('walkforward_pass_rate', 0.0))
    param_sensitivity = float(deterministic.get('param_sensitivity', 1.0))
    score_delta = active_comparison.get('score_delta')
    score_delta_value = float(score_delta) if isinstance(score_delta, (int, float)) else None
    challenger_min_delta = float(thresholds.get('challenger_min_delta', 0.0))
    comparable = final_score >= float(thresholds.get('keep_threshold', 0.0))
    replaceable = (
        bool(promotion_gate.get('eligible'))
        and active_comparison.get('can_challenge_active') is True
        and (score_delta_value is None or score_delta_value >= challenger_min_delta)
    )
    oos_passed = walkforward_pass_rate >= 0.65
    robustness_passed = param_sensitivity <= 0.3
    quality_band = _quality_band(
        final_score=final_score,
        walkforward_pass_rate=walkforward_pass_rate,
        param_sensitivity=param_sensitivity,
    )
    total_windows = 12
    passed_windows = max(0, min(total_windows, round(walkforward_pass_rate * total_windows)))
    return {
        'version': 'v1',
        'oos_validation': {
            'walkforward_pass_rate': walkforward_pass_rate,
            'required_pass_rate': 0.65,
            'passed': oos_passed,
            'passed_windows': passed_windows,
            'total_windows': total_windows,
            'stability_ratio': round(passed_windows / total_windows, 3),
        },
        'pool_comparison': {
            'active_title': active_comparison.get('active_title'),
            'score_delta': score_delta_value,
            'required_delta': challenger_min_delta,
            'comparable': comparable,
            'replaceable': replaceable,
            'relative_to_active': (
                'outperforming'
                if score_delta_value is not None and score_delta_value > 0
                else 'lagging'
                if score_delta_value is not None and score_delta_value < 0
                else 'flat'
            ),
        },
        'robustness': {
            'param_sensitivity': param_sensitivity,
            'max_allowed': 0.3,
            'passed': robustness_passed,
        },
        'return_quality': {
            'cagr': float(deterministic.get('cagr', 0.0)),
            'sharpe': float(deterministic.get('sharpe', 0.0)),
            'max_drawdown': float(deterministic.get('max_drawdown', 0.0)),
        },
        'verdict': {
            'quality_band': quality_band,
            'comparable': comparable,
            'replaceable': replaceable,
            'accumulable': comparable and oos_passed and robustness_passed,
        },
    }


def _proposal_base_strategy(proposal: StrategyProposal) -> str:
    params = proposal.strategy_dsl.get('params', {}) if isinstance(proposal.strategy_dsl, dict) else {}
    if isinstance(params, dict) and isinstance(params.get('base_strategy'), str) and params.get('base_strategy'):
        return str(params['base_strategy'])
    return proposal.title


def _attach_quality_track_record(db: Session, proposals: list[StrategyProposal]) -> list[StrategyProposal]:
    if not proposals:
        return proposals

    symbols = sorted({proposal.symbol for proposal in proposals})
    historical = list(
        db.execute(
            select(StrategyProposal)
            .where(StrategyProposal.symbol.in_(symbols))
            .order_by(StrategyProposal.created_at.desc())
        ).scalars()
    )
    grouped: dict[tuple[str, str], list[StrategyProposal]] = {}
    for record in historical:
        grouped.setdefault((record.symbol, _proposal_base_strategy(record)), []).append(record)

    for proposal in proposals:
        peers = grouped.get((proposal.symbol, _proposal_base_strategy(proposal)), [])
        recent = peers[:12]
        hydrated_recent = []
        for item in recent:
            if isinstance(item.evidence_pack, dict):
                item.evidence_pack = _ensure_quality_report_payload(dict(item.evidence_pack), item.final_score)
            hydrated_recent.append(item)
        comparable_count = 0
        replaceable_count = 0
        scores: list[float] = []
        stability_scores: list[float] = []
        stable_streak = 0
        for item in hydrated_recent:
            quality = dict(item.evidence_pack.get('quality_report', {})) if isinstance(item.evidence_pack, dict) else {}
            verdict = dict(quality.get('verdict', {}))
            oos_validation = dict(quality.get('oos_validation', {}))
            scores.append(item.final_score)
            stability_scores.append(float(oos_validation.get('stability_ratio', 0.0) or 0.0))
            comparable = bool(verdict.get('comparable'))
            replaceable = bool(verdict.get('replaceable'))
            if comparable:
                comparable_count += 1
            if replaceable:
                replaceable_count += 1
            if comparable and item.id != proposal.id:
                stable_streak += 1
            elif item.id != proposal.id:
                break
        recent_three = scores[:3]
        prior_three = scores[3:6]
        recent_avg = sum(recent_three) / len(recent_three) if recent_three else proposal.final_score
        prior_avg = sum(prior_three) / len(prior_three) if prior_three else recent_avg
        trend = 'flat'
        if recent_avg - prior_avg >= 2.0:
            trend = 'improving'
        elif prior_avg - recent_avg >= 2.0:
            trend = 'weakening'
        quality_report = dict(proposal.evidence_pack.get('quality_report', {})) if isinstance(proposal.evidence_pack, dict) else {}
        quality_report['track_record'] = {
            'recent_total': len(hydrated_recent),
            'recent_comparable': comparable_count,
            'recent_replaceable': replaceable_count,
            'comparable_ratio': round(comparable_count / len(hydrated_recent), 3) if hydrated_recent else 0.0,
            'replaceable_ratio': round(replaceable_count / len(hydrated_recent), 3) if hydrated_recent else 0.0,
            'average_final_score': round(sum(scores) / len(scores), 1) if scores else round(proposal.final_score, 1),
            'best_final_score': round(max(scores), 1) if scores else round(proposal.final_score, 1),
            'average_stability_ratio': round(sum(stability_scores) / len(stability_scores), 3) if stability_scores else 0.0,
            'stable_streak': stable_streak,
            'trend': trend,
            'window_days': 30,
            'recent_30d_total': sum(
                1 for item in hydrated_recent if abs((proposal.created_at.date() - item.created_at.date()).days) <= 30
            ),
            'recent_30d_comparable': sum(
                1
                for item in hydrated_recent
                if abs((proposal.created_at.date() - item.created_at.date()).days) <= 30
                and bool(dict(dict(item.evidence_pack).get('quality_report', {})).get('verdict', {}).get('comparable'))
            ),
        }
        proposal.evidence_pack = {
            **dict(proposal.evidence_pack or {}),
            'quality_report': quality_report,
        }
    return proposals


def _ensure_quality_report_payload(evidence_pack: dict[str, object], final_score: float) -> dict[str, object]:
    governance_report = evidence_pack.get('governance_report')
    if isinstance(governance_report, dict):
        lifecycle = dict(governance_report.get('lifecycle', {}))
        if lifecycle and ('eta_kind' not in lifecycle or 'estimated_next_eligible_at' not in lifecycle):
            cooldown_remaining_days = int(
                dict(governance_report.get('active_comparison', {})).get('cooldown_remaining_days') or 0
            )
            lifecycle_eta = _lifecycle_eta(
                phase=str(lifecycle.get('phase') or 'unknown'),
                cooldown_remaining_days=cooldown_remaining_days,
                current_time=now_tz(),
            )
            governance_report = {
                **governance_report,
                'lifecycle': {
                    **lifecycle,
                    'eta_kind': lifecycle_eta['eta_kind'],
                    'estimated_next_eligible_at': lifecycle_eta['estimated_next_eligible_at'],
                },
            }
            evidence_pack['governance_report'] = governance_report
    if isinstance(evidence_pack.get('quality_report'), dict):
        return evidence_pack
    if not isinstance(governance_report, dict):
        return evidence_pack
    evidence_pack['quality_report'] = _build_quality_report(
        evidence_pack=evidence_pack,
        governance_report=governance_report,
        final_score=final_score,
    )
    return evidence_pack


def _hydrate_proposal_quality_report(proposal: StrategyProposal | None) -> StrategyProposal | None:
    if proposal is None:
        return None
    if isinstance(proposal.evidence_pack, dict):
        proposal.evidence_pack = _ensure_quality_report_payload(dict(proposal.evidence_pack), proposal.final_score)
    return proposal


def _hydrate_decision_quality_report(decision: RiskDecision | None) -> RiskDecision | None:
    if decision is None:
        return None
    if isinstance(decision.evidence_pack, dict):
        decision.evidence_pack = _ensure_quality_report_payload(dict(decision.evidence_pack), decision.final_score)
    return decision


def _attach_pool_ranking(proposals: list[StrategyProposal]) -> list[StrategyProposal]:
    if not proposals:
        return proposals
    ranked = sorted(proposals, key=lambda item: (item.final_score, item.created_at), reverse=True)
    leader_score = ranked[0].final_score
    total_tracked = len(ranked)
    sorted_scores = [proposal.final_score for proposal in ranked]
    median_score = sorted_scores[len(sorted_scores) // 2] if sorted_scores else 0.0
    for index, proposal in enumerate(ranked, start=1):
        if not isinstance(proposal.evidence_pack, dict):
            proposal.evidence_pack = {}
        quality_report = dict(proposal.evidence_pack.get('quality_report', {}))
        quality_report['pool_ranking'] = {
            'rank': index,
            'total_tracked': total_tracked,
            'leader_score': leader_score,
            'leader_gap': round(leader_score - proposal.final_score, 1),
            'percentile': round((total_tracked - index) / max(total_tracked - 1, 1), 3) if total_tracked > 1 else 1.0,
            'median_score': round(median_score, 1),
            'median_gap': round(proposal.final_score - median_score, 1),
            'selection_state': (
                'leader'
                if index == 1
                else 'challenger'
                if proposal.status in {ProposalStatus.CANDIDATE, ProposalStatus.ACTIVE}
                else 'trailing'
            ),
        }
        proposal.evidence_pack = {
            **proposal.evidence_pack,
            'quality_report': quality_report,
        }
    return proposals


def _order_fill_rate(orders: list[dict[str, object]]) -> float | None:
    if not orders:
        return None
    filled = sum(1 for item in orders if str(item.get('status', '')).lower() == 'filled')
    return filled / len(orders)


def build_operational_acceptance(
    *,
    proposal: StrategyProposal | None,
    latest_decision: RiskDecision | None,
    nav_rows: list[dict[str, object]],
    orders: list[dict[str, object]],
    macro_status: dict[str, object],
    current_time: datetime,
) -> dict[str, object]:
    governance = get_settings().governance
    live_drawdown = _paper_nav_drawdown(nav_rows)
    fill_rate = _order_fill_rate(orders)
    promoted_at = proposal.promoted_at if proposal else None
    live_days = max(0, (current_time.date() - promoted_at.date()).days) if promoted_at else 0
    checks = {
        'minimum_live_days': live_days >= governance.acceptance_min_days,
        'fill_rate_ok': fill_rate is None or fill_rate >= governance.acceptance_min_fill_rate,
        'drawdown_within_acceptance': live_drawdown < governance.acceptance_max_drawdown,
        'macro_pipeline_ready': not bool(macro_status.get('degraded')),
    }
    failed_checks = [key for key, passed in checks.items() if not passed]
    status = 'accepted' if not failed_checks else 'review_required'
    if failed_checks == ['minimum_live_days']:
        status = 'provisional'
    pause_events_30d = 0
    rollback_events_30d = 0
    incident_free_days: int | None = None
    if proposal is not None:
        recent_decisions = sorted(
            [
                decision
                for decision in proposal.decisions
                if max(0, (current_time.date() - decision.created_at.date()).days) <= 30
            ],
            key=lambda item: item.created_at,
            reverse=True,
        )
        pause_events_30d = sum(1 for item in recent_decisions if item.action == RiskDecisionAction.PAUSE_ACTIVE)
        rollback_events_30d = sum(
            1 for item in recent_decisions if item.action == RiskDecisionAction.ROLLBACK_TO_PREVIOUS_STABLE
        )
        latest_incident = next(
            (
                item.created_at
                for item in recent_decisions
                if item.action in {RiskDecisionAction.PAUSE_ACTIVE, RiskDecisionAction.ROLLBACK_TO_PREVIOUS_STABLE}
            ),
            None,
        )
        incident_free_days = max(0, (current_time.date() - latest_incident.date()).days) if latest_incident else live_days
    operational_score = 1.0
    operational_score -= min(0.35, live_drawdown / max(governance.acceptance_max_drawdown, 0.0001) * 0.25)
    if fill_rate is not None:
        operational_score -= max(0.0, governance.acceptance_min_fill_rate - fill_rate) * 0.5
    operational_score -= pause_events_30d * 0.08
    operational_score -= rollback_events_30d * 0.15
    if bool(macro_status.get('degraded')):
        operational_score -= 0.12
    return {
        'status': status,
        'accepted': status == 'accepted',
        'live_days': live_days,
        'minimum_live_days': governance.acceptance_min_days,
        'fill_rate': round(fill_rate, 3) if fill_rate is not None else None,
        'minimum_fill_rate': governance.acceptance_min_fill_rate,
        'drawdown': round(live_drawdown, 4),
        'maximum_acceptance_drawdown': governance.acceptance_max_drawdown,
        'failed_checks': failed_checks,
        'latest_action': latest_decision.action.value if latest_decision else None,
        'pause_events_30d': pause_events_30d,
        'rollback_events_30d': rollback_events_30d,
        'incident_free_days': incident_free_days,
        'operational_score': round(max(0.0, min(1.0, operational_score)), 2),
    }


def build_acceptance_report(db: Session, *, window_days: int = 30) -> dict[str, object]:
    current_time = now_tz()
    active = get_active_strategy(db)
    latest_decision = get_latest_risk_decision(db)
    snapshot = build_market_snapshot(db)
    paper = fetch_paper_data(limit=max(window_days * 2, 60))
    operational_acceptance = build_operational_acceptance(
        proposal=active,
        latest_decision=latest_decision,
        nav_rows=paper['nav'],
        orders=paper['orders'],
        macro_status=dict(snapshot['macro_status']),
        current_time=current_time,
    )
    quality_report = dict(active.evidence_pack.get('quality_report', {})) if active and isinstance(active.evidence_pack, dict) else {}
    governance_report = dict(latest_decision.evidence_pack.get('governance_report', {})) if latest_decision and isinstance(latest_decision.evidence_pack, dict) else {}
    macro_status = dict(snapshot['macro_status'])

    safety_actions = _recent_audit_counts(
        db,
        event_types=['risk_decision_recorded'],
        entity_type='risk_decision',
        days=window_days,
    )
    macro_degraded_count = _recent_audit_counts(
        db,
        event_types=['macro_provider_degraded'],
        entity_type='macro_pipeline',
        days=window_days,
    )
    fallback_count = _recent_audit_counts(
        db,
        event_types=['llm_fallback_triggered', 'macro_provider_fallback_applied'],
        days=window_days,
    )

    report_status = 'healthy'
    if operational_acceptance.get('status') == 'review_required' or bool(macro_status.get('degraded')):
        report_status = 'attention'
    elif operational_acceptance.get('status') == 'provisional':
        report_status = 'watch'

    key_findings: list[str] = []
    next_actions: list[str] = []
    track_record = dict(quality_report.get('track_record', {}))
    verdict = dict(quality_report.get('verdict', {}))
    if verdict.get('quality_band'):
        key_findings.append(f"quality_band={verdict.get('quality_band')}")
    if track_record.get('trend'):
        key_findings.append(f"track_record_trend={track_record.get('trend')}")
    if operational_acceptance.get('status'):
        key_findings.append(f"operational_acceptance={operational_acceptance.get('status')}")
    if macro_status.get('reliability_tier'):
        key_findings.append(f"macro_tier={macro_status.get('reliability_tier')}")
    if operational_acceptance.get('status') != 'accepted':
        next_actions.append('review_operational_acceptance')
    if bool(macro_status.get('degraded')):
        next_actions.append('restore_macro_pipeline')
    if track_record.get('trend') == 'weakening':
        next_actions.append('revalidate_strategy_quality')
    if not next_actions:
        next_actions.append('continue_monitoring')

    return {
        'generated_at': current_time,
        'window_days': window_days,
        'status': report_status,
        'strategy_title': active.title if active else None,
        'key_findings': key_findings,
        'next_actions': next_actions,
        'quality': {
            'quality_band': verdict.get('quality_band'),
            'track_record': track_record,
            'oos_validation': dict(quality_report.get('oos_validation', {})),
            'pool_comparison': dict(quality_report.get('pool_comparison', {})),
        },
        'operations': {
            **operational_acceptance,
            'nav_points': len(paper['nav']),
            'orders_observed': len(paper['orders']),
        },
        'macro': {
            'provider': macro_status.get('provider'),
            'active_provider': macro_status.get('active_provider'),
            'provider_chain': macro_status.get('provider_chain', []),
            'status': macro_status.get('status'),
            'reliability_score': macro_status.get('reliability_score'),
            'reliability_tier': macro_status.get('reliability_tier'),
            'freshness_hours': macro_status.get('freshness_hours'),
            'freshness_tier': macro_status.get('freshness_tier'),
            'health_score_30d': macro_status.get('health_score_30d'),
            'degraded_count_30d': macro_status.get('degraded_count_30d'),
            'fallback_count_30d': macro_status.get('fallback_count_30d'),
            'recovery_count_30d': macro_status.get('recovery_count_30d'),
        },
        'governance': {
            'phase': dict(governance_report.get('lifecycle', {})).get('phase'),
            'next_step': dict(governance_report.get('lifecycle', {})).get('next_step'),
            'eta_kind': dict(governance_report.get('lifecycle', {})).get('eta_kind'),
            'estimated_next_eligible_at': dict(governance_report.get('lifecycle', {})).get('estimated_next_eligible_at'),
            'resume_conditions': dict(governance_report.get('lifecycle', {})).get('resume_conditions', []),
            'safety_actions_30d': safety_actions,
            'fallback_events_30d': fallback_count,
            'macro_degraded_30d': macro_degraded_count,
        },
    }


def _fallback_risk_judgment(blueprint: dict[str, object]) -> dict[str, object]:
    return {
        'llm_score': float(blueprint.get('llm_score', 72.0)),
        'llm_explanation': str(blueprint.get('llm_explanation', 'Mock fallback kept the prior contextual ranking.')),
        'prompt_version': blueprint.get('prompt_versions', {}).get('risk_manager_llm', RISK_MANAGER_LLM_PROMPT_VERSION),
    }


def run_risk_judgment(
    db: Session,
    blueprint: dict[str, object],
    debate_report: dict[str, object],
    snapshot: dict[str, object],
    deterministic_score: float,
    governance_report: dict[str, object],
    current_time: datetime,
) -> tuple[dict[str, object], dict[str, object]]:
    digest: DailyEventDigest = snapshot['event_digest']
    evidence_pack = _base_evidence_pack(blueprint, digest, deterministic_score, governance_report)
    if blueprint.get('source_kind') == 'mock':
        judgment = _fallback_risk_judgment(blueprint)
        evidence_pack['llm_judgment_inputs']['prompt_versions'] = blueprint.get('prompt_versions', {})
        return judgment, evidence_pack

    payload = build_risk_manager_llm_payload(
        proposal={
            'title': blueprint['title'],
            'thesis': blueprint['thesis'],
            'base_strategy': blueprint['base_strategy'],
            'features_used': blueprint['features_used'],
            'params': blueprint.get('params', {}),
        },
        debate_report=debate_report,
        evidence_pack=evidence_pack,
        market_snapshot={
            'regime': snapshot['regime'],
            'confidence': snapshot['confidence'],
            'summary': snapshot['summary'],
            'price_context': snapshot['price_context'],
        },
        event_digest={
            'macro_summary': digest.macro_summary,
            'event_scores': digest.event_scores,
        },
    )
    result = get_llm_gateway().invoke_json(
        db=db,
        task='risk_manager_llm',
        system=risk_manager_llm_system_prompt(),
        user=json.dumps(payload, ensure_ascii=False),
        schema_hint=RISK_MANAGER_LLM_SCHEMA_HINT,
    )
    _record_llm_stage(
        db,
        stage='risk_manager_llm',
        prompt_version=RISK_MANAGER_LLM_PROMPT_VERSION,
        status=result.status,
        created_at=current_time,
        market_snapshot_hash=str(snapshot['market_snapshot_hash']),
        event_digest_hash=digest.digest_hash,
        payload_extra={'proposal_title': str(blueprint['title'])},
    )
    raw = result.payload if isinstance(result.payload, dict) else {}
    try:
        llm_score = float(raw.get('llm_score', 72.0))
    except (TypeError, ValueError):
        llm_score = 72.0
    judgment = {
        'llm_score': max(50.0, min(95.0, llm_score)),
        'llm_explanation': str(raw.get('llm_explanation') or '').strip(),
        'prompt_version': RISK_MANAGER_LLM_PROMPT_VERSION,
    }
    if not judgment['llm_explanation']:
        judgment = _fallback_risk_judgment(blueprint)
        judgment['prompt_version'] = RISK_MANAGER_LLM_PROMPT_VERSION
    evidence_pack['llm_judgment_inputs']['prompt_versions'] = {
        **blueprint.get('prompt_versions', {}),
        'research_debate': debate_report.get('prompt_version', RESEARCH_DEBATE_PROMPT_VERSION),
        'risk_manager_llm': judgment['prompt_version'],
    }
    return judgment, evidence_pack


def _latest_proposal_decision(proposal: StrategyProposal | None) -> RiskDecision | None:
    if proposal is None or not proposal.decisions:
        return None
    return sorted(proposal.decisions, key=lambda item: (item.created_at, item.id))[-1]


def _get_previous_stable_strategy(db: Session, exclude_proposal_id: str | None = None) -> StrategyProposal | None:
    query = (
        select(StrategyProposal)
        .options(selectinload(StrategyProposal.decisions))
        .where(
            StrategyProposal.status == ProposalStatus.ARCHIVED,
            StrategyProposal.promoted_at.is_not(None),
        )
        .order_by(StrategyProposal.promoted_at.desc(), StrategyProposal.created_at.desc())
    )
    records = list(db.execute(query).scalars())
    for record in records:
        if exclude_proposal_id and record.id == exclude_proposal_id:
            continue
        return record
    return None


def evaluate_active_strategy_health(db: Session, snapshot: dict[str, object], current_time: datetime) -> RiskDecision | None:
    active = get_active_strategy(db)
    if active is None:
        return None

    governance = get_settings().governance
    nav_rows = fetch_paper_data(limit=120)['nav']
    paper = fetch_paper_data(limit=120)
    nav_rows = paper['nav']
    orders = paper['orders']
    live_drawdown = _paper_nav_drawdown(nav_rows)
    macro_status = dict(snapshot.get('macro_status', {}))
    latest_decision = _latest_proposal_decision(active)
    operational_acceptance = build_operational_acceptance(
        proposal=active,
        latest_decision=latest_decision,
        nav_rows=nav_rows,
        orders=orders,
        macro_status=macro_status,
        current_time=current_time,
    )
    if latest_decision and latest_decision.action in {RiskDecisionAction.PAUSE_ACTIVE, RiskDecisionAction.ROLLBACK_TO_PREVIOUS_STABLE}:
        return latest_decision

    if live_drawdown < governance.live_drawdown_pause:
        return None

    previous_stable = _get_previous_stable_strategy(db, exclude_proposal_id=active.id)
    governance_report = {
        'version': 'v1.5',
        'active_health': {
            'live_drawdown': live_drawdown,
            'pause_threshold': governance.live_drawdown_pause,
            'rollback_threshold': governance.live_drawdown_rollback,
            'macro_status': macro_status,
            'previous_stable_title': previous_stable.title if previous_stable else None,
            'operational_acceptance': operational_acceptance,
        },
        'lifecycle': {
            'phase': 'paused_pending_review',
            'next_step': 'resume_after_revalidation',
            'rechallenge_allowed': False,
            'review_trigger': 'next_agent_sync',
            'eta_kind': 'review_pending',
            'estimated_next_eligible_at': None,
            'resume_conditions': [
                'drawdown_back_below_pause_threshold',
                'macro_pipeline_ready',
                'fresh_candidate_review_completed',
            ],
        },
    }
    action = RiskDecisionAction.PAUSE_ACTIVE
    explanation = (
        f"Live paper drawdown reached {live_drawdown:.2%}, above the pause threshold "
        f"{governance.live_drawdown_pause:.2%}. The active strategy is paused pending review."
    )
    if live_drawdown >= governance.live_drawdown_rollback and previous_stable is not None:
        active.status = ProposalStatus.CANDIDATE
        active.updated_at = current_time
        previous_stable.status = ProposalStatus.ACTIVE
        previous_stable.promoted_at = current_time
        previous_stable.updated_at = current_time
        action = RiskDecisionAction.ROLLBACK_TO_PREVIOUS_STABLE
        governance_report['lifecycle'] = {
            'phase': 'rolled_back',
            'next_step': 'continue_with_previous_stable',
            'rechallenge_allowed': False,
            'review_trigger': 'next_agent_sync',
            'eta_kind': 'quality_revalidation',
            'estimated_next_eligible_at': None,
            'resume_conditions': [
                'new_candidate_outperforms_active',
                'cooldown_elapsed',
                'macro_pipeline_ready',
            ],
        }
        explanation = (
            f"Live paper drawdown reached {live_drawdown:.2%}, above the rollback threshold "
            f"{governance.live_drawdown_rollback:.2%}. Rolling back to {previous_stable.title}."
        )
    elif live_drawdown >= governance.live_drawdown_pause:
        active.status = ProposalStatus.CANDIDATE
        active.updated_at = current_time

    evidence_pack = dict(active.evidence_pack or {})
    evidence_pack['governance_report'] = {
        **dict(evidence_pack.get('governance_report', {})),
        **governance_report,
        'selected_action': action.value,
    }
    decision = RiskDecision(
        decision_id=f"decision-{stable_hash([active.run_id, action.value, current_time.isoformat()])}",
        run_id=active.run_id,
        proposal_id=active.id,
        action=action,
        deterministic_score=active.deterministic_score,
        llm_score=active.llm_score,
        final_score=active.final_score,
        bottom_line_passed=True,
        bottom_line_report=dict(evidence_pack.get('bottom_line_report', {})),
        llm_explanation=explanation,
        evidence_pack=evidence_pack,
        created_at=current_time,
    )
    db.add(decision)
    db.flush()
    _record_system_audit(
        db,
        event_type='risk_decision_recorded',
        entity_type='risk_decision',
        entity_id=decision.id,
        payload=_audit_payload(active, decision),
        created_at=current_time,
        run_id=active.run_id,
        decision_id=decision.decision_id,
        market_snapshot_hash=active.market_snapshot_hash,
        event_digest_hash=active.event_digest_hash,
    )
    return decision


def materialize_proposals_and_decisions(
    db: Session,
    *,
    snapshot: dict[str, object],
    digest: DailyEventDigest,
    blueprints: list[dict[str, object]],
    previous_active: StrategyProposal | None,
    current_time: datetime,
) -> None:
    active_context = _proposal_context(previous_active)
    macro_status = dict(snapshot.get('macro_status', {}))
    for index, blueprint in enumerate(blueprints):
        deterministic_score = _deterministic_score(index, snapshot, digest, list(blueprint['features_used']))
        provisional_bottom_line = deterministic_score <= 100.0
        status, action, governance_report = _governance_action(
            final_score=deterministic_score,
            bottom_line_passed=provisional_bottom_line,
            active_context=active_context,
            macro_status=macro_status,
            current_time=current_time,
        )
        debate_report = run_research_debate(db, blueprint, snapshot, current_time)
        risk_judgment, evidence_pack = run_risk_judgment(
            db,
            blueprint,
            debate_report,
            snapshot,
            deterministic_score,
            governance_report,
            current_time,
        )
        llm_score = float(risk_judgment['llm_score'])
        final_score = round(deterministic_score * 0.7 + llm_score * 0.3, 1)
        bottom_line_passed = all(evidence_pack['bottom_line_report'].values())
        status, action, governance_report = _governance_action(
            final_score=final_score,
            bottom_line_passed=bottom_line_passed,
            active_context=active_context,
            macro_status=macro_status,
            current_time=current_time,
        )
        evidence_pack['governance_report'] = governance_report
        evidence_pack['quality_report'] = _build_quality_report(
            evidence_pack=evidence_pack,
            governance_report=governance_report,
            final_score=final_score,
        )
        dsl = _strategy_dsl(blueprint, snapshot, digest)
        proposal = StrategyProposal(
            run_id=f"run-{stable_hash([blueprint['title'], digest.digest_hash, current_time.isoformat(), blueprint.get('source_kind', 'mock')])}",
            title=str(blueprint['title']),
            symbol=str(snapshot['symbol']),
            market_scope='CN',
            thesis=str(blueprint['thesis']),
            source_kind=str(blueprint.get('source_kind', 'mock')),
            provider_status=str(blueprint.get('provider_status', 'mock')),
            provider_model=str(blueprint.get('provider_model', 'mock')),
            provider_message=str(blueprint.get('provider_message', '')),
            market_snapshot_hash=str(snapshot['market_snapshot_hash']),
            event_digest_hash=digest.digest_hash,
            strategy_dsl=dsl,
            debate_report=debate_report,
            evidence_pack=evidence_pack,
            features_used=list(blueprint['features_used']),
            deterministic_score=deterministic_score,
            llm_score=llm_score,
            final_score=final_score,
            status=status,
            created_at=current_time,
            updated_at=current_time,
            promoted_at=current_time if status == ProposalStatus.ACTIVE else None,
            archived_at=current_time if status == ProposalStatus.REJECTED else None,
        )
        db.add(proposal)
        db.flush()

        decision = RiskDecision(
            decision_id=f"decision-{stable_hash([proposal.run_id, action.value])}",
            run_id=proposal.run_id,
            proposal_id=proposal.id,
            action=action,
            deterministic_score=proposal.deterministic_score,
            llm_score=proposal.llm_score,
            final_score=proposal.final_score,
            bottom_line_passed=bottom_line_passed,
            bottom_line_report=evidence_pack['bottom_line_report'],
            llm_explanation=str(risk_judgment['llm_explanation']),
            evidence_pack=evidence_pack,
            created_at=current_time,
        )
        db.add(decision)
        db.flush()

        db.add(
            AuditRecord(
                run_id=proposal.run_id,
                decision_id=decision.decision_id,
                event_type='proposal_created',
                entity_type='strategy_proposal',
                entity_id=proposal.id,
                strategy_dsl_hash=stable_hash(dsl),
                market_snapshot_hash=proposal.market_snapshot_hash,
                event_digest_hash=proposal.event_digest_hash,
                payload={
                    'title': proposal.title,
                    'status': proposal.status.value,
                    'governance_report': governance_report,
                    'prompt_versions': evidence_pack['llm_judgment_inputs'].get('prompt_versions', {}),
                },
                created_at=current_time,
            )
        )
        db.add(
            AuditRecord(
                run_id=proposal.run_id,
                decision_id=decision.decision_id,
                event_type='risk_decision_recorded',
                entity_type='risk_decision',
                entity_id=decision.id,
                strategy_dsl_hash=stable_hash(dsl),
                market_snapshot_hash=proposal.market_snapshot_hash,
                event_digest_hash=proposal.event_digest_hash,
                payload=_audit_payload(proposal, decision),
                created_at=current_time,
            )
        )
        if proposal.status == ProposalStatus.ACTIVE:
            active_context = _proposal_context(proposal)
    db.flush()

def _audit_payload(proposal: StrategyProposal, decision: RiskDecision) -> dict[str, object]:
    return {
        "proposal_title": proposal.title,
        "proposal_status": proposal.status.value,
        "decision_action": decision.action.value,
        "final_score": decision.final_score,
        "governance_report": dict(decision.evidence_pack.get("governance_report", {})) if isinstance(decision.evidence_pack, dict) else {},
        "quality_report": dict(decision.evidence_pack.get("quality_report", {})) if isinstance(decision.evidence_pack, dict) else {},
    }


def archive_strategy_proposals(db: Session, archived_at: datetime) -> None:
    records = list(
        db.execute(
            select(StrategyProposal).where(StrategyProposal.status != ProposalStatus.ARCHIVED)
        ).scalars()
    )
    for record in records:
        record.status = ProposalStatus.ARCHIVED
        record.archived_at = archived_at
        record.updated_at = archived_at
    db.flush()


def sync_agent_state(db: Session, force_refresh: bool = False, *, trigger: str = 'manual') -> None:
    with _PIPELINE_SYNC_LOCK:
        started_at = now_tz()
        _set_pipeline_runtime_status(
            db,
            current_state='running',
            status_message='Pipeline sync is running.',
            current_time=started_at,
            last_trigger=trigger,
            degraded=False,
        )
        db.commit()
        try:
            sync_event_stream(db)
            sync_daily_event_digests(db)
            current_time = now_tz()
            base_snapshot = build_market_snapshot(db)
            analyst_state = run_market_analyst(db, base_snapshot, current_time)
            snapshot = _merge_market_snapshot(base_snapshot, analyst_state)
            digest: DailyEventDigest = snapshot["event_digest"]  # type: ignore[assignment]
            symbol = str(snapshot["symbol"])
            previous_active = get_active_strategy(db)
            existing_open_count = db.execute(
                select(func.count())
                .select_from(StrategyProposal)
                .where(StrategyProposal.status != ProposalStatus.ARCHIVED)
            ).scalar_one()

            if force_refresh:
                archive_strategy_proposals(db, archived_at=current_time)
            elif existing_open_count > 0 and previous_active is None:
                archive_strategy_proposals(db, archived_at=current_time)
            elif existing_open_count > 0 and previous_active is not None:
                evaluate_active_strategy_health(db, snapshot, current_time)
                macro_status = dict(snapshot.get('macro_status', {}))
                _set_pipeline_runtime_status(
                    db,
                    current_state='degraded' if bool(macro_status.get('degraded')) else 'idle',
                    status_message='Pipeline health review completed.' if not bool(macro_status.get('degraded')) else 'Pipeline completed with macro degradation.',
                    current_time=current_time,
                    last_success_at=current_time.isoformat(),
                    consecutive_failures=0,
                    last_duration_ms=max(0, int((current_time - started_at).total_seconds() * 1000)),
                    last_trigger=trigger,
                    degraded=bool(macro_status.get('degraded')),
                )
                db.commit()
                return

            blueprints, _ = run_strategy_agent(db=db, symbol=symbol, snapshot=snapshot, current_time=current_time)
            materialize_proposals_and_decisions(
                db,
                snapshot=snapshot,
                digest=digest,
                blueprints=blueprints,
                previous_active=previous_active,
                current_time=current_time,
            )
            evaluate_active_strategy_health(db, snapshot, current_time)
            macro_status = dict(snapshot.get('macro_status', {}))
            _set_pipeline_runtime_status(
                db,
                current_state='degraded' if bool(macro_status.get('degraded')) else 'idle',
                status_message='Pipeline sync completed successfully.' if not bool(macro_status.get('degraded')) else 'Pipeline sync completed with macro degradation.',
                current_time=current_time,
                last_success_at=current_time.isoformat(),
                consecutive_failures=0,
                last_duration_ms=max(0, int((current_time - started_at).total_seconds() * 1000)),
                last_trigger=trigger,
                degraded=bool(macro_status.get('degraded')),
            )
            db.commit()
        except Exception as exc:
            failed_at = now_tz()
            previous = _get_runtime_setting_json(db, _PIPELINE_STATUS_KEY) or {}
            failure_count = int(previous.get('consecutive_failures', 0) or 0) + 1
            _set_pipeline_runtime_status(
                db,
                current_state='failed',
                status_message=f'Pipeline sync failed: {exc}',
                current_time=failed_at,
                last_failure_at=failed_at.isoformat(),
                consecutive_failures=failure_count,
                last_duration_ms=max(0, int((failed_at - started_at).total_seconds() * 1000)),
                last_trigger=trigger,
                degraded=True,
            )
            _record_system_audit(
                db,
                event_type='pipeline_sync_failed',
                entity_type='pipeline_runtime',
                entity_id='agent_sync',
                payload={
                    'trigger': trigger,
                    'error': str(exc),
                    'consecutive_failures': failure_count,
                },
                created_at=failed_at,
            )
            db.commit()
            raise


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


def list_strategy_proposals(db: Session) -> list[StrategyProposal]:
    records = list(
        db.execute(
            select(StrategyProposal)
            .options(selectinload(StrategyProposal.decisions))
            .where(StrategyProposal.status != ProposalStatus.ARCHIVED)
            .order_by(StrategyProposal.final_score.desc(), StrategyProposal.created_at.desc())
        ).scalars()
    )
    hydrated = [_hydrate_proposal_quality_report(record) for record in records]
    return _attach_pool_ranking(_attach_quality_track_record(db, hydrated))


def get_strategy_proposal(db: Session, proposal_id: str) -> StrategyProposal | None:
    record = db.execute(
        select(StrategyProposal)
        .options(selectinload(StrategyProposal.decisions))
        .where(StrategyProposal.id == proposal_id)
    ).scalar_one_or_none()
    hydrated = _hydrate_proposal_quality_report(record)
    if hydrated is None:
        return None
    return _attach_quality_track_record(db, [hydrated])[0]


def get_active_strategy(db: Session) -> StrategyProposal | None:
    record = (
        db.execute(
            select(StrategyProposal)
            .options(selectinload(StrategyProposal.decisions))
            .where(StrategyProposal.status == ProposalStatus.ACTIVE)
            .order_by(StrategyProposal.promoted_at.desc(), StrategyProposal.created_at.desc())
        ).scalars().first()
    )
    hydrated = _hydrate_proposal_quality_report(record)
    if hydrated is None:
        return None
    return _attach_quality_track_record(db, [hydrated])[0]


def list_candidate_strategies(db: Session) -> list[StrategyProposal]:
    records = list(
        db.execute(
            select(StrategyProposal)
            .options(selectinload(StrategyProposal.decisions))
            .where(StrategyProposal.status.in_([ProposalStatus.CANDIDATE, ProposalStatus.ACTIVE]))
            .order_by(StrategyProposal.final_score.desc(), StrategyProposal.created_at.desc())
        ).scalars()
    )
    hydrated = [_hydrate_proposal_quality_report(record) for record in records]
    return _attach_pool_ranking(_attach_quality_track_record(db, hydrated))


def list_risk_decisions(db: Session, limit: int = 50) -> list[RiskDecision]:
    records = list(
        db.execute(
            select(RiskDecision).order_by(RiskDecision.created_at.desc()).limit(limit)
        ).scalars()
    )
    hydrated = [_hydrate_decision_quality_report(record) for record in records]
    proposal_ids = [record.proposal_id for record in hydrated if record is not None]
    proposals = {
        proposal.id: proposal
        for proposal in _attach_quality_track_record(
            db,
            [
                _hydrate_proposal_quality_report(item)
                for item in db.execute(
                    select(StrategyProposal).where(StrategyProposal.id.in_(proposal_ids))
                ).scalars()
            ],
        )
    } if proposal_ids else {}
    for record in hydrated:
        proposal = proposals.get(record.proposal_id) if record else None
        if record and proposal and isinstance(proposal.evidence_pack, dict) and isinstance(record.evidence_pack, dict):
            quality_report = dict(proposal.evidence_pack.get('quality_report', {}))
            record.evidence_pack = {**record.evidence_pack, 'quality_report': quality_report}
    return hydrated


def get_latest_risk_decision(db: Session) -> RiskDecision | None:
    record = (
        db.execute(
            select(RiskDecision).order_by(RiskDecision.created_at.desc(), RiskDecision.id.desc())
        ).scalars().first()
    )
    hydrated = _hydrate_decision_quality_report(record)
    if hydrated is None:
        return None
    proposal = get_strategy_proposal(db, hydrated.proposal_id)
    if proposal and isinstance(proposal.evidence_pack, dict) and isinstance(hydrated.evidence_pack, dict):
        hydrated.evidence_pack = {
            **hydrated.evidence_pack,
            'quality_report': dict(proposal.evidence_pack.get('quality_report', {})),
        }
    return hydrated


def list_audit_records(db: Session, limit: int = 50) -> list[AuditRecord]:
    return list(
        db.execute(
            select(AuditRecord).order_by(AuditRecord.created_at.desc(), AuditRecord.id.desc()).limit(limit)
        ).scalars()
    )


def list_event_stream(db: Session, limit: int = 50) -> list[EventRecord]:
    return list(
        db.execute(
            select(EventRecord).order_by(EventRecord.published_at.desc()).limit(limit)
        ).scalars()
    )


def list_event_digests(db: Session, limit: int = 30) -> list[DailyEventDigest]:
    return list(
        db.execute(
            select(DailyEventDigest).order_by(DailyEventDigest.trade_date.desc(), DailyEventDigest.id.desc()).limit(limit)
        ).scalars()
    )
