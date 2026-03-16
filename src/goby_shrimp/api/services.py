from __future__ import annotations

import hashlib
import inspect
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
from ..data import get_provider, get_source_manager
from ..data.hk_universe import fetch_hk_universe_candidates
from ..data.symbols import detect_market, normalize_symbol
from ..events import EventSeed, get_event_providers
from ..llm_gateway import LLMProvider, get_llm_gateway
from ..market_profile import get_market_profile
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
from ..models import Verdict
from ..risk import risk_gate_review
from ..runtime_state import get_runtime_state_json, set_runtime_state_json
from ..strategy import (
    get_strategy_factory,
    get_strategy_registry,
    get_strategy_knowledge,
    knowledge_payload_for_market,
    knowledge_preferences_from_market_profile,
)
from ..strategy.signals import Signal
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
    StrategyProposal,
    StrategySnapshot,
)

_MACRO_STATUS_KEY = "events.macro.status"
_PIPELINE_STATUS_KEY = "pipeline.runtime.status"
_UNIVERSE_SELECTION_KEY = "universe.selection"
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
    record = get_runtime_state_json(_MACRO_STATUS_KEY)
    if record is None:
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
    value = dict(record)
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
        'current_stage': None,
        'stage_started_at': None,
        'stage_durations_ms': {},
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
    last_run_at = status.get('last_run_at')
    if current_state == 'running' and isinstance(last_run_at, str) and last_run_at:
        try:
            last_run_dt = datetime.fromisoformat(last_run_at)
            stale_after = timedelta(minutes=max(interval_minutes * 2, 15))
            stalled = now_tz() - last_run_dt > stale_after
        except ValueError:
            stalled = False
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
        'current_stage': status.get('current_stage'),
        'stage_started_at': status.get('stage_started_at'),
        'stage_durations_ms': dict(status.get('stage_durations_ms', {}) or {}),
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
    current_stage: str | None = None,
) -> None:
    previous = _get_runtime_setting_json(db, _PIPELINE_STATUS_KEY) or {}
    interval_minutes = max(5, get_settings().events.expected_sync_interval_minutes)
    previous_state = str(previous.get('current_state', 'idle'))
    previous_stage = previous.get('current_stage')
    previous_stage_started_at = previous.get('stage_started_at')
    if current_state == 'running' and previous_state != 'running':
        stage_durations: dict[str, int] = {}
    else:
        stage_durations = dict(previous.get('stage_durations_ms', {}) or {})

    if isinstance(previous_stage, str) and isinstance(previous_stage_started_at, str):
        try:
            previous_stage_dt = datetime.fromisoformat(previous_stage_started_at)
        except ValueError:
            previous_stage_dt = None
        if previous_stage_dt is not None:
            if current_state == 'running' and current_stage and current_stage != previous_stage:
                elapsed = max(0, int((current_time - previous_stage_dt).total_seconds() * 1000))
                stage_durations[previous_stage] = int(stage_durations.get(previous_stage, 0) or 0) + elapsed
            elif previous_state == 'running' and current_state != 'running':
                elapsed = max(0, int((current_time - previous_stage_dt).total_seconds() * 1000))
                stage_durations[previous_stage] = int(stage_durations.get(previous_stage, 0) or 0) + elapsed

    if current_state == 'running':
        effective_stage = current_stage if current_stage is not None else previous_stage
        if current_stage is not None and current_stage != previous_stage:
            stage_started_at = current_time.isoformat()
        else:
            stage_started_at = previous.get('stage_started_at') or current_time.isoformat()
    else:
        effective_stage = None
        stage_started_at = None

    payload = {
        'current_state': current_state,
        'status_message': status_message,
        'current_stage': effective_stage,
        'stage_started_at': stage_started_at,
        'stage_durations_ms': stage_durations,
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


def _set_pipeline_runtime_stage(
    db: Session,
    *,
    stage: str,
    current_time: datetime,
    status_message: str,
    trigger: str,
) -> None:
    _set_pipeline_runtime_status(
        db,
        current_state='running',
        status_message=status_message,
        current_time=current_time,
        last_trigger=trigger,
        degraded=False,
        current_stage=stage,
    )
    db.commit()


def set_runtime_llm_provider(db: Session, provider: str):
    current_provider = get_llm_gateway().get_provider(db)
    status = get_llm_gateway().set_provider(db, provider)
    audit_time = now_tz()
    success = not (status.provider == LLMProvider.MINIMAX and status.status == "missing_key")
    decision_id = f"llm-provider-{stable_hash([current_provider, provider, audit_time.isoformat()])}"
    payload = {
        "old_provider": current_provider,
        "new_provider": status.provider,
        "status": status.status,
        "message": status.message,
        "success": success,
    }
    for event_type, entity_id, event_payload in [
        ("llm_provider_changed", status.provider, payload),
        ("llm_provider_switched", status.provider, payload),
        (
            "provider_cohort_started",
            status.provider,
            {
                **payload,
                "cohort_provider": status.provider,
                "cohort_started_at": audit_time.isoformat(),
            },
        ),
        (
            "provider_comparison_window_closed",
            current_provider,
            {
                "provider": current_provider,
                "next_provider": status.provider,
                "window_closed_at": audit_time.isoformat(),
                "reason": "provider_switched",
            },
        ),
    ]:
        db.add(
            AuditRecord(
                run_id="system-llm-gateway",
                decision_id=decision_id,
                event_type=event_type,
                entity_type="llm_gateway",
                entity_id=entity_id,
                strategy_dsl_hash="",
                market_snapshot_hash="",
                event_digest_hash="",
                payload=event_payload,
                created_at=audit_time,
            )
        )
    db.commit()
    if not success:
        return status, False
    return status, True


def _provider_cohort_windows(db: Session, *, window_days: int = 30) -> list[dict[str, object]]:
    since = now_tz() - timedelta(days=window_days)
    rows = list(
        db.execute(
            select(AuditRecord)
            .where(
                AuditRecord.event_type == "provider_cohort_started",
                AuditRecord.created_at >= since,
            )
            .order_by(AuditRecord.created_at.asc(), AuditRecord.id.asc())
        ).scalars()
    )
    windows: list[dict[str, object]] = []
    for index, row in enumerate(rows):
        payload = dict(row.payload or {})
        next_row = rows[index + 1] if index + 1 < len(rows) else None
        provider = str(payload.get("cohort_provider") or payload.get("new_provider") or row.entity_id)
        windows.append(
            {
                "provider": provider,
                "cohort_started_at": row.created_at,
                "cohort_closed_at": next_row.created_at if next_row is not None else None,
            }
        )
    current_provider = get_current_llm_status(db).provider
    if not windows:
        windows.append(
            {
                "provider": current_provider,
                "cohort_started_at": since,
                "cohort_closed_at": None,
            }
        )
    elif str(windows[-1].get("provider")) != current_provider:
        windows.append(
            {
                "provider": current_provider,
                "cohort_started_at": since,
                "cohort_closed_at": None,
            }
        )
    return windows[-3:]


def _build_provider_cohort_metrics(
    db: Session,
    *,
    provider: str,
    cohort_started_at: datetime | None,
    cohort_closed_at: datetime | None,
) -> dict[str, object]:
    query = select(StrategyProposal)
    if cohort_started_at is not None:
        query = query.where(StrategyProposal.created_at >= cohort_started_at)
    if cohort_closed_at is not None:
        query = query.where(StrategyProposal.created_at < cohort_closed_at)
    proposals = list(db.execute(query.order_by(StrategyProposal.created_at.asc())).scalars())

    if provider == "mock":
        real = [proposal for proposal in proposals if proposal.source_kind == "mock"]
        fallback = []
        cohort_total = len(real)
    else:
        real = [proposal for proposal in proposals if proposal.source_kind == provider]
        fallback = [proposal for proposal in proposals if proposal.source_kind == "mock"]
        cohort_total = len(real) + len(fallback)

    promoted = [
        proposal
        for proposal in real
        if proposal.promoted_at is not None or proposal.status == ProposalStatus.ACTIVE
    ]
    promoted_symbols: dict[str, int] = {}
    for proposal in promoted:
        promoted_symbols[proposal.symbol] = promoted_symbols.get(proposal.symbol, 0) + 1
    avg_final_score = None
    if real:
        avg_final_score = round(sum(float(proposal.final_score or 0.0) for proposal in real) / len(real), 1)

    return {
        "provider": provider,
        "cohort_started_at": cohort_started_at.isoformat() if cohort_started_at is not None else None,
        "cohort_closed_at": cohort_closed_at.isoformat() if cohort_closed_at is not None else None,
        "proposal_count": cohort_total,
        "real_proposal_count": len(real),
        "fallback_count": len(fallback),
        "fallback_rate": round((len(fallback) / cohort_total), 3) if cohort_total else 0.0,
        "promoted_count": len(promoted),
        "promotion_rate": round((len(promoted) / len(real)), 3) if real else 0.0,
        "avg_final_score": avg_final_score,
        "promoted_symbol_distribution": promoted_symbols,
    }


def build_provider_migration_summary(db: Session, *, window_days: int = 30) -> dict[str, object]:
    cohorts = _provider_cohort_windows(db, window_days=window_days)
    current_provider = str(get_current_llm_status(db).provider)
    current_window = next((cohort for cohort in reversed(cohorts) if str(cohort.get("provider")) == current_provider), cohorts[-1])
    current_metrics = _build_provider_cohort_metrics(
        db,
        provider=str(current_window.get("provider")),
        cohort_started_at=current_window.get("cohort_started_at"),
        cohort_closed_at=current_window.get("cohort_closed_at"),
    )
    previous_window = None
    for cohort in reversed(cohorts[:-1]):
        if str(cohort.get("provider")) != current_provider:
            previous_window = cohort
            break
    previous_metrics = None
    if previous_window is not None:
        previous_metrics = _build_provider_cohort_metrics(
            db,
            provider=str(previous_window.get("provider")),
            cohort_started_at=previous_window.get("cohort_started_at"),
            cohort_closed_at=previous_window.get("cohort_closed_at"),
        )

    deltas: dict[str, float] = {}
    notes: list[str] = []
    if previous_metrics is not None:
        previous_avg = previous_metrics.get("avg_final_score")
        current_avg = current_metrics.get("avg_final_score")
        if isinstance(current_avg, (int, float)) and isinstance(previous_avg, (int, float)):
            deltas["avg_final_score"] = round(float(current_avg) - float(previous_avg), 1)
        deltas["promotion_rate"] = round(
            float(current_metrics.get("promotion_rate", 0.0) or 0.0) - float(previous_metrics.get("promotion_rate", 0.0) or 0.0),
            3,
        )
        deltas["fallback_rate"] = round(
            float(current_metrics.get("fallback_rate", 0.0) or 0.0) - float(previous_metrics.get("fallback_rate", 0.0) or 0.0),
            3,
        )
    if float(current_metrics.get("fallback_rate", 0.0) or 0.0) > 0:
        notes.append("Current provider cohort still contains mock fallback output and should be compared with caution.")
    if int(current_metrics.get("real_proposal_count", 0) or 0) < 3:
        notes.append("Current provider cohort is still thin; proposal quality comparisons are directional, not conclusive.")
    if previous_metrics is None:
        notes.append("No prior provider cohort is available in the current comparison window.")

    if previous_metrics is not None:
        summary = (
            f"Current cohort runs on {current_provider} with "
            f"{current_metrics['real_proposal_count']} real proposals, "
            f"{round(float(current_metrics.get('promotion_rate', 0.0) or 0.0) * 100, 1)}% promotion rate, and "
            f"{round(float(current_metrics.get('fallback_rate', 0.0) or 0.0) * 100, 1)}% fallback contamination."
        )
    else:
        summary = (
            f"Current cohort runs on {current_provider} with "
            f"{current_metrics['real_proposal_count']} real proposals in the active comparison window."
        )

    return {
        "comparison_window_days": window_days,
        "current_provider": current_provider,
        "current_cohort_started_at": current_metrics.get("cohort_started_at"),
        "previous_provider": previous_metrics.get("provider") if previous_metrics is not None else None,
        "switch_detected": previous_metrics is not None,
        "summary": summary,
        "notes": notes,
        "current": current_metrics,
        "previous": previous_metrics,
        "deltas": deltas,
    }


def build_provider_migration_history(db: Session, *, window_days: int = 30) -> list[dict[str, object]]:
    cohorts = _provider_cohort_windows(db, window_days=window_days)
    if not cohorts:
        return []
    current_provider = str(get_current_llm_status(db).provider)
    history: list[dict[str, object]] = []
    for cohort in cohorts:
        provider = str(cohort.get("provider"))
        metrics = _build_provider_cohort_metrics(
            db,
            provider=provider,
            cohort_started_at=cohort.get("cohort_started_at"),
            cohort_closed_at=cohort.get("cohort_closed_at"),
        )
        started_at = metrics.get("cohort_started_at")
        label = provider
        if isinstance(started_at, str) and started_at:
            label = f"{provider} @ {started_at[5:10]}"
        history.append(
            {
                **metrics,
                "label": label,
                "is_current": provider == current_provider and metrics.get("cohort_closed_at") is None,
            }
        )
    return history


def build_runtime_sync_history(db: Session, *, limit: int = 8) -> list[dict[str, object]]:
    rows = list(
        db.execute(
            select(AuditRecord)
            .where(AuditRecord.event_type.in_(['pipeline_sync_completed', 'pipeline_sync_failed']))
            .order_by(AuditRecord.created_at.desc(), AuditRecord.id.desc())
            .limit(limit)
        ).scalars()
    )
    history: list[dict[str, object]] = []
    for audit in rows:
        payload = dict(audit.payload or {})
        stage_durations = {
            str(key): int(value)
            for key, value in dict(payload.get('stage_durations_ms', {}) or {}).items()
        }
        history.append({
            'created_at': audit.created_at,
            'state': 'failed' if audit.event_type == 'pipeline_sync_failed' else str(payload.get('state', 'idle')),
            'trigger': str(payload.get('trigger')) if payload.get('trigger') is not None else None,
            'total_duration_ms': int(payload['last_duration_ms']) if payload.get('last_duration_ms') is not None else None,
            'stage_durations_ms': stage_durations,
            'current_stage': str(payload.get('current_stage')) if payload.get('current_stage') is not None else None,
            'status_message': str(payload.get('status_message')) if payload.get('status_message') is not None else None,
            'degraded': bool(payload.get('degraded', False)),
        })
    return history


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
    conn = _open_sqlite(path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.OperationalError:
        rows = []
    finally:
        conn.close()
    return rows


def _open_sqlite(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


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
                "SELECT trade_date, cash, position_value, total_equity FROM daily_nav ORDER BY trade_date DESC, rowid DESC LIMIT ?",
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


def get_latest_paper_execution(db: Session, proposal: StrategyProposal | None) -> dict[str, object] | None:
    if proposal is None:
        return None
    record = db.execute(
        select(AuditRecord)
        .where(
            AuditRecord.entity_type == 'paper_runtime',
            AuditRecord.entity_id == proposal.id,
            AuditRecord.event_type.in_(['paper_execution_cycle', 'paper_execution_skipped']),
        )
        .order_by(AuditRecord.created_at.desc(), AuditRecord.id.desc())
    ).scalars().first()
    if record is None:
        return None
    payload = dict(record.payload or {})
    target_quantity = int(payload['target_quantity']) if payload.get('target_quantity') is not None else None
    current_quantity = int(payload['current_quantity']) if payload.get('current_quantity') is not None else None
    order_quantity = int(payload['order_quantity']) if payload.get('order_quantity') is not None else None
    signal_value = str(payload.get('signal') or 'HOLD')
    try:
        signal = Signal[signal_value]
    except KeyError:
        signal = Signal.HOLD
    explanation_key = payload.get('explanation_key')
    explanation = payload.get('explanation')
    skip_message = str(payload.get('message') or '')
    if record.event_type == 'paper_execution_skipped' and (explanation_key is None or explanation is None):
        if skip_message == 'market_closed_non_trading_day':
            explanation_key = explanation_key or 'market_closed_non_trading_day'
            explanation = explanation or 'Paper execution was skipped because today is not a trading day for this market.'
        elif skip_message == 'market_closed_outside_session':
            explanation_key = explanation_key or 'market_closed_outside_session'
            explanation = explanation or 'Paper execution was skipped because the market is outside its trading session.'
    if explanation_key is None or explanation is None:
        derived_key, derived_explanation = _paper_execution_explanation(
            trade_qty=abs(order_quantity or 0),
            price_changed=bool(payload.get('price_changed', False)),
            equity_changed=bool(payload.get('equity_changed', False)),
            target_qty=target_quantity or 0,
            current_qty=current_quantity or 0,
            signal=signal,
        )
        explanation_key = explanation_key or derived_key
        explanation = explanation or derived_explanation
    return {
        'status': 'skipped' if record.event_type == 'paper_execution_skipped' else 'executed',
        'executed_at': record.created_at.isoformat(),
        'reason': payload.get('reason'),
        'signal': payload.get('signal'),
        'target_quantity': target_quantity,
        'current_quantity': current_quantity,
        'order_side': payload.get('order_side'),
        'order_quantity': order_quantity,
        'latest_price': float(payload['latest_price']) if payload.get('latest_price') is not None else None,
        'cash': float(payload['cash']) if payload.get('cash') is not None else None,
        'position_value': float(payload['position_value']) if payload.get('position_value') is not None else None,
        'total_equity': float(payload['total_equity']) if payload.get('total_equity') is not None else None,
        'latest_price_as_of': payload.get('latest_price_as_of'),
        'price_age_hours': float(payload['price_age_hours']) if payload.get('price_age_hours') is not None else None,
        'price_changed': bool(payload.get('price_changed', False)),
        'equity_changed': bool(payload.get('equity_changed', False)),
        'rebalance_triggered': bool(payload.get('rebalance_triggered', False)),
        'explanation_key': explanation_key,
        'explanation': explanation,
        'message': payload.get('message'),
    }


def _quote_age_hours(*, current_time: datetime, as_of: str | None) -> float | None:
    if not as_of:
        return None
    try:
        parsed = datetime.fromisoformat(as_of)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo(get_settings().timezone))
    return round(max(0.0, (current_time - parsed).total_seconds() / 3600), 2)


def _paper_execution_explanation(
    *,
    trade_qty: int,
    price_changed: bool,
    equity_changed: bool,
    target_qty: int,
    current_qty: int,
    signal: Signal,
) -> tuple[str, str]:
    if trade_qty > 0:
        return (
            'rebalance_executed',
            'This cycle changed the target position and generated a paper trade.',
        )
    if target_qty == current_qty and not price_changed:
        return (
            'price_unchanged_position_held',
            'No rebalance was required because both the target position and the latest mark price were unchanged.',
        )
    if target_qty == current_qty and price_changed and not equity_changed:
        return (
            'position_held_rounding_flat',
            'The position stayed unchanged and the latest marked price did not change portfolio equity after rounding.',
        )
    if target_qty == current_qty:
        return (
            'signal_holds_position',
            'The current signal keeps the existing position, so no new paper order was generated.',
        )
    return (
        f'signal_{signal.value.lower()}_no_trade',
        'The latest signal did not require a rebalance in this execution cycle.',
    )


def _paper_snapshot_db_paths() -> list[str]:
    settings = get_settings()
    paths = [settings.storage.runtime_db_path, settings.storage.paper_db_path]
    unique_paths: list[str] = []
    for path in paths:
        if path not in unique_paths:
            unique_paths.append(path)
    return unique_paths


def _ensure_paper_snapshot_tables(db_path: str) -> None:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = _open_sqlite(path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_nav (
                trade_date TEXT NOT NULL,
                cash REAL NOT NULL,
                position_value REAL NOT NULL,
                total_equity REAL NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                price REAL NOT NULL,
                amount REAL NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                avg_cost REAL NOT NULL,
                market_value REAL NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def _proposal_has_paper_snapshot(proposal_id: str, db: Session) -> bool:
    return (
        db.execute(
            select(func.count())
            .select_from(AuditRecord)
            .where(
                AuditRecord.event_type == 'paper_snapshot_initialized',
                AuditRecord.entity_type == 'paper_runtime',
                AuditRecord.entity_id == proposal_id,
            )
        ).scalar_one()
        > 0
    )


def _initialize_paper_snapshot_for_proposal(
    db: Session,
    *,
    proposal: StrategyProposal,
    current_time: datetime,
    decision_id: str | None,
    reason: str,
) -> bool:
    if _proposal_has_paper_snapshot(proposal.id, db):
        return False

    initial_equity = float(get_settings().portfolio.default_capital)
    trade_date = current_time.date().isoformat()
    written_paths: list[str] = []
    for db_path in _paper_snapshot_db_paths():
        _ensure_paper_snapshot_tables(db_path)
        conn = _open_sqlite(db_path)
        try:
            conn.execute(
                """
                INSERT INTO daily_nav (trade_date, cash, position_value, total_equity)
                VALUES (?, ?, ?, ?)
                """,
                (trade_date, initial_equity, 0.0, initial_equity),
            )
            conn.commit()
            written_paths.append(db_path)
        finally:
            conn.close()

    db.add(
        AuditRecord(
            run_id=proposal.run_id,
            decision_id=decision_id or f"paper-snapshot-{stable_hash([proposal.id, trade_date, reason])}",
            event_type='paper_snapshot_initialized',
            entity_type='paper_runtime',
            entity_id=proposal.id,
            strategy_dsl_hash=stable_hash(proposal.strategy_dsl),
            market_snapshot_hash=proposal.market_snapshot_hash,
            event_digest_hash=proposal.event_digest_hash,
            payload={
                'title': proposal.title,
                'symbol': proposal.symbol,
                'trade_date': trade_date,
                'cash': initial_equity,
                'position_value': 0.0,
                'total_equity': initial_equity,
                'db_paths': written_paths,
                'reason': reason,
            },
            created_at=current_time,
        )
    )
    db.flush()
    return True


def _market_lot_size(symbol: str) -> int:
    market = detect_market(symbol)
    return 100 if market in {'hk', 'cn'} else 1


def _market_scope_from_symbol_or_scope(*, symbol: str | None = None, market_scope: str | None = None) -> str:
    resolved_scope = (market_scope or "").strip().upper()
    if not resolved_scope and symbol:
        market = detect_market(symbol)
        resolved_scope = {"hk": "HK", "cn": "CN", "us": "US"}.get(market, "HK")
    return resolved_scope or "HK"


def _is_trading_day(*, current_time: datetime, symbol: str | None = None, market_scope: str | None = None) -> bool:
    resolved_scope = _market_scope_from_symbol_or_scope(symbol=symbol, market_scope=market_scope)
    return current_time.weekday() < 5 if resolved_scope in {"HK", "CN", "US"} else True


def _paper_market_is_open(*, current_time: datetime, symbol: str | None = None, market_scope: str | None = None) -> tuple[bool, str]:
    resolved_scope = _market_scope_from_symbol_or_scope(symbol=symbol, market_scope=market_scope)
    if not _is_trading_day(current_time=current_time, market_scope=resolved_scope):
        return False, 'market_closed_non_trading_day'
    current_minutes = current_time.hour * 60 + current_time.minute
    if resolved_scope == 'HK':
        return (9 * 60 + 30) <= current_minutes < (16 * 60), 'market_closed_outside_session'
    if resolved_scope == 'CN':
        return (9 * 60 + 30) <= current_minutes < (15 * 60), 'market_closed_outside_session'
    return True, 'market_open'


def _append_daily_nav_if_needed(
    conn: sqlite3.Connection,
    *,
    trade_date: str,
    cash: float,
    position_value: float,
    total_equity: float,
) -> bool:
    latest_row = conn.execute(
        """
        SELECT trade_date, cash, position_value, total_equity
        FROM daily_nav
        ORDER BY trade_date DESC, rowid DESC
        LIMIT 1
        """
    ).fetchone()
    if latest_row is not None:
        same_trade_date = str(latest_row[0]) == trade_date
        same_cash = abs(float(latest_row[1]) - cash) <= 1e-9
        same_position_value = abs(float(latest_row[2]) - position_value) <= 1e-9
        same_total_equity = abs(float(latest_row[3]) - total_equity) <= 1e-9
        if same_trade_date and same_cash and same_position_value and same_total_equity:
            return False
    conn.execute(
        """
        INSERT INTO daily_nav (trade_date, cash, position_value, total_equity)
        VALUES (?, ?, ?, ?)
        """,
        (trade_date, cash, position_value, total_equity),
    )
    return True


def _paper_trade_already_bootstrapped(proposal_id: str, db: Session) -> bool:
    return (
        db.execute(
            select(func.count())
            .select_from(AuditRecord)
            .where(
                AuditRecord.event_type == 'paper_trade_bootstrapped',
                AuditRecord.entity_type == 'paper_runtime',
                AuditRecord.entity_id == proposal_id,
            )
        ).scalar_one()
        > 0
    )


def _latest_paper_nav_state() -> dict[str, float]:
    paper = fetch_paper_data(limit=1)
    latest_nav = paper['nav'][0] if paper['nav'] else None
    initial_equity = float(get_settings().portfolio.default_capital)
    if latest_nav is None:
        return {
            'trade_date': None,
            'cash': initial_equity,
            'position_value': 0.0,
            'total_equity': initial_equity,
        }
    return {
        'trade_date': latest_nav.get('trade_date'),
        'cash': float(latest_nav.get('cash', initial_equity) or initial_equity),
        'position_value': float(latest_nav.get('position_value', 0.0) or 0.0),
        'total_equity': float(latest_nav.get('total_equity', initial_equity) or initial_equity),
    }


def _latest_paper_position(symbol: str) -> dict[str, object] | None:
    paper = fetch_paper_data(limit=50)
    normalized_symbol = normalize_symbol(symbol, market=detect_market(symbol))
    for position in paper['positions']:
        if normalize_symbol(str(position.get('symbol', '')), market=detect_market(str(position.get('symbol', '')))) == normalized_symbol:
            return position
    return None


def _sanitize_strategy_params(base_strategy: str, params: dict[str, object]) -> dict[str, object]:
    registry = get_strategy_registry()
    definition = registry.get(base_strategy)
    candidate_cls = definition.stream_cls or definition.vectorized_cls
    if candidate_cls is None:
        return {}
    try:
        signature = inspect.signature(candidate_cls)
    except (TypeError, ValueError):
        return dict(params)
    allowed = {
        name
        for name, parameter in signature.parameters.items()
        if name != 'self' and parameter.kind in {inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY}
    }
    return {key: value for key, value in params.items() if key in allowed}


def _proposal_base_strategy_from_spec(title: str, strategy_dsl: dict[str, object] | None) -> str:
    params = strategy_dsl.get('params', {}) if isinstance(strategy_dsl, dict) else {}
    if isinstance(params, dict) and isinstance(params.get('base_strategy'), str) and params.get('base_strategy'):
        return str(params['base_strategy'])
    return title


def _strategy_adapter_from_spec(title: str, strategy_dsl: dict[str, object] | None):
    params = strategy_dsl.get('params', {}) if isinstance(strategy_dsl, dict) else {}
    base_strategy = _proposal_base_strategy_from_spec(title, strategy_dsl)
    strategy_params = dict(params) if isinstance(params, dict) else {}
    strategy_params.pop('base_strategy', None)
    strategy_params.pop('symbol', None)
    sanitized = _sanitize_strategy_params(base_strategy, strategy_params)
    return get_strategy_factory().create(name=base_strategy, mode="auto", params=sanitized)


def _proposal_strategy_adapter(proposal: StrategyProposal):
    return _strategy_adapter_from_spec(proposal.title, proposal.strategy_dsl)


def _proposal_backtest_gate(
    *,
    title: str,
    symbol: str,
    strategy_dsl: dict[str, object],
    current_time: datetime,
) -> dict[str, object]:
    settings = get_settings()
    lookback_years = max(int(settings.hard_gates.min_data_years), 3) + 1
    start_date = (current_time - timedelta(days=365 * lookback_years)).date().isoformat()
    end_date = current_time.date().isoformat()
    try:
        strategy = _strategy_adapter_from_spec(title, strategy_dsl)
        result = BacktestEngine().run(
            ticker=symbol,
            strategy=strategy,
            start_date=start_date,
            end_date=end_date,
            initial_capital=float(settings.portfolio.default_capital),
            is_first_live=bool(settings.yellow_flags.first_live_deployment),
        )
        review = risk_gate_review(result)
        blocked_reasons: list[str] = []
        if review.verdict == Verdict.NO_GO:
            blocked_reasons.append('backtest_no_go')
        elif review.requires_human_approve:
            blocked_reasons.append('backtest_review_required')
        elif review.verdict == Verdict.REVISE:
            blocked_reasons.append('backtest_requires_revision')
        eligible_for_paper = review.verdict == Verdict.GO and not review.requires_human_approve
        return {
            'available': True,
            'eligible_for_paper': eligible_for_paper,
            'blocked_reasons': blocked_reasons,
            'summary': (
                'Backtest admission passed for paper promotion.'
                if eligible_for_paper
                else review.reasoning or 'Backtest admission blocked this proposal from paper promotion.'
            ),
            'metrics': result.model_dump(),
            'review': review.model_dump(),
            'window': {
                'start_date': start_date,
                'end_date': end_date,
                'lookback_years': lookback_years,
            },
        }
    except Exception as exc:
        return {
            'available': False,
            'eligible_for_paper': False,
            'blocked_reasons': ['backtest_unavailable'],
            'summary': f'Backtest admission was unavailable: {exc}',
            'metrics': {},
            'review': {
                'verdict': Verdict.REVISE.value,
                'requires_human_approve': False,
                'hard_gates_failed': [],
                'yellow_flags_triggered': [],
                'utility_score': None,
                'reasoning': str(exc),
            },
            'window': {
                'start_date': start_date,
                'end_date': end_date,
                'lookback_years': lookback_years,
            },
        }


def _backtest_gate_bottom_line(gate: dict[str, object]) -> bool:
    return bool(gate.get('available')) and bool(gate.get('eligible_for_paper'))


def _backtest_metrics_for_evidence(gate: dict[str, object]) -> dict[str, float]:
    metrics = dict(gate.get('metrics', {}) or {})
    out: dict[str, float] = {}
    for key in ('cagr', 'sharpe', 'max_drawdown', 'annual_turnover', 'data_years', 'param_sensitivity'):
        value = metrics.get(key)
        if isinstance(value, (int, float)):
            out[key] = float(value)
    return out


def _load_execution_history(symbol: str, current_time: datetime):
    history_end = current_time.date().isoformat()
    history_start = (current_time - timedelta(days=220)).date().isoformat()
    return get_source_manager().fetch_ohlcv(symbol, history_start, history_end)


def _current_target_quantity(
    *,
    proposal: StrategyProposal,
    latest_price: float,
    current_equity: float,
    signal: Signal,
) -> int:
    if latest_price <= 0:
        return 0
    if signal == Signal.SELL:
        return 0
    if signal != Signal.BUY:
        current_position = _latest_paper_position(proposal.symbol)
        return int(current_position.get('quantity', 0) or 0) if current_position else 0

    sizing = proposal.strategy_dsl.get('position_sizing', {}) if isinstance(proposal.strategy_dsl, dict) else {}
    sizing_value = float(sizing.get('value', 0.25)) if isinstance(sizing, dict) else 0.25
    sizing_value = max(0.05, min(0.5, sizing_value))
    target_notional = max(0.0, current_equity) * sizing_value
    lot_size = _market_lot_size(proposal.symbol)
    quantity = int(target_notional // latest_price)
    quantity = max(lot_size, (quantity // lot_size) * lot_size)
    return max(0, quantity)


def _record_paper_execution_audit(
    db: Session,
    *,
    proposal: StrategyProposal,
    current_time: datetime,
    event_type: str,
    payload: dict[str, object],
) -> None:
    db.add(
        AuditRecord(
            run_id=proposal.run_id,
            decision_id=f"{event_type}-{stable_hash([proposal.id, current_time.isoformat(), payload])}",
            event_type=event_type,
            entity_type='paper_runtime',
            entity_id=proposal.id,
            strategy_dsl_hash=stable_hash(proposal.strategy_dsl),
            market_snapshot_hash=proposal.market_snapshot_hash,
            event_digest_hash=proposal.event_digest_hash,
            payload=payload,
            created_at=current_time,
        )
    )
    db.flush()


def execute_active_paper_cycle(
    db: Session,
    *,
    proposal: StrategyProposal,
    current_time: datetime,
    reason: str,
) -> dict[str, object]:
    _initialize_paper_snapshot_for_proposal(
        db,
        proposal=proposal,
        current_time=current_time,
        decision_id=None,
        reason=reason,
    )
    history = _load_execution_history(proposal.symbol, current_time)
    if history is None or history.empty:
        _record_paper_execution_audit(
            db,
            proposal=proposal,
            current_time=current_time,
            event_type='paper_execution_skipped',
            payload={
                'reason': reason,
                'message': 'history_unavailable',
                'symbol': proposal.symbol,
            },
        )
        return {'executed': False, 'reason': 'history_unavailable'}

    latest_bar = history.iloc[-1]
    latest_bar_index = history.index[-1]
    latest_price = float(latest_bar['close'])
    latest_price_as_of = latest_bar_index.to_pydatetime().isoformat() if hasattr(latest_bar_index, 'to_pydatetime') else str(latest_bar_index)
    price_age_hours = _quote_age_hours(current_time=current_time, as_of=latest_price_as_of)
    market_open, market_message = _paper_market_is_open(
        current_time=current_time,
        symbol=proposal.symbol,
        market_scope=proposal.market_scope,
    )
    nav_state = _latest_paper_nav_state()
    current_position = _latest_paper_position(proposal.symbol)
    current_qty = int(current_position.get('quantity', 0) or 0) if current_position else 0
    current_avg_cost = float(current_position.get('avg_cost', latest_price) or latest_price) if current_position else latest_price
    previous_execution = get_latest_paper_execution(db, proposal)
    strategy = _proposal_strategy_adapter(proposal)
    signal = strategy.generate_signal(history)
    target_qty = _current_target_quantity(
        proposal=proposal,
        latest_price=latest_price,
        current_equity=float(nav_state['total_equity']),
        signal=signal,
    )
    holding_constraints = proposal.strategy_dsl.get('holding_constraints', {}) if isinstance(proposal.strategy_dsl, dict) else {}
    min_holding_days = int(holding_constraints.get('min_holding_days', 0) or 0) if isinstance(holding_constraints, dict) else 0
    latest_buy_order = next(
        (
            order for order in fetch_paper_data(limit=200)['orders']
            if normalize_symbol(str(order.get('symbol', '')), market=detect_market(str(order.get('symbol', '')))) == normalize_symbol(proposal.symbol, market=detect_market(proposal.symbol))
            and str(order.get('side', '')).lower() == 'buy'
        ),
        None,
    )
    if target_qty < current_qty and latest_buy_order and min_holding_days > 0:
        try:
            latest_buy_at = datetime.fromisoformat(str(latest_buy_order.get('created_at')))
        except ValueError:
            latest_buy_at = None
        if latest_buy_at is not None and (current_time.date() - latest_buy_at.date()).days < min_holding_days:
            target_qty = current_qty

    if not market_open:
        new_cash = float(nav_state['cash'])
        new_position_value = round(current_qty * latest_price, 2)
        new_total_equity = round(new_cash + new_position_value, 2)
        previous_price = float(previous_execution['latest_price']) if previous_execution and previous_execution.get('latest_price') is not None else None
        previous_total_equity = float(previous_execution['total_equity']) if previous_execution and previous_execution.get('total_equity') is not None else float(nav_state['total_equity'])
        price_changed = previous_price is None or abs(previous_price - latest_price) > 1e-9
        equity_changed = abs(previous_total_equity - new_total_equity) > 1e-9
        trade_date = current_time.date().isoformat()
        nav_written = False
        if equity_changed or str(nav_state.get('trade_date') or '') != trade_date:
            for db_path in _paper_snapshot_db_paths():
                _ensure_paper_snapshot_tables(db_path)
                conn = _open_sqlite(db_path)
                try:
                    nav_written = _append_daily_nav_if_needed(
                        conn,
                        trade_date=trade_date,
                        cash=new_cash,
                        position_value=new_position_value,
                        total_equity=new_total_equity,
                    ) or nav_written
                    conn.commit()
                finally:
                    conn.close()

        _record_paper_execution_audit(
            db,
            proposal=proposal,
            current_time=current_time,
            event_type='paper_execution_skipped',
            payload={
                'reason': reason,
                'message': market_message,
                'symbol': proposal.symbol,
                'latest_price': latest_price,
                'latest_price_as_of': latest_price_as_of,
                'price_age_hours': price_age_hours,
                'price_changed': price_changed,
                'equity_changed': equity_changed,
                'rebalance_triggered': False,
                'current_quantity': current_qty,
                'target_quantity': current_qty,
                'order_quantity': 0,
                'cash': new_cash,
                'position_value': new_position_value,
                'total_equity': new_total_equity,
                'nav_written': nav_written,
            },
        )
        return {
            'executed': False,
            'reason': market_message,
            'latest_price': latest_price,
            'latest_price_as_of': latest_price_as_of,
            'price_age_hours': price_age_hours,
            'price_changed': price_changed,
            'equity_changed': equity_changed,
            'rebalance_triggered': False,
            'current_quantity': current_qty,
            'target_quantity': current_qty,
            'cash': new_cash,
            'position_value': new_position_value,
            'total_equity': new_total_equity,
        }

    order_qty = target_qty - current_qty
    order_side = 'buy' if order_qty > 0 else 'sell' if order_qty < 0 else None
    trade_qty = abs(order_qty)
    amount = round(trade_qty * latest_price, 2)
    new_cash = float(nav_state['cash'])
    new_avg_cost = current_avg_cost
    if order_side == 'buy':
        new_cash = round(max(0.0, new_cash - amount), 2)
        new_avg_cost = (
            round(((current_qty * current_avg_cost) + amount) / max(target_qty, 1), 4)
            if current_qty > 0 else latest_price
        )
    elif order_side == 'sell':
        new_cash = round(new_cash + amount, 2)
        if target_qty <= 0:
            new_avg_cost = 0.0

    new_position_value = round(target_qty * latest_price, 2)
    new_total_equity = round(new_cash + new_position_value, 2)
    previous_price = float(previous_execution['latest_price']) if previous_execution and previous_execution.get('latest_price') is not None else None
    previous_total_equity = float(previous_execution['total_equity']) if previous_execution and previous_execution.get('total_equity') is not None else float(nav_state['total_equity'])
    price_changed = previous_price is None or abs(previous_price - latest_price) > 1e-9
    equity_changed = abs(previous_total_equity - new_total_equity) > 1e-9
    explanation_key, explanation = _paper_execution_explanation(
        trade_qty=trade_qty,
        price_changed=price_changed,
        equity_changed=equity_changed,
        target_qty=target_qty,
        current_qty=current_qty,
        signal=signal,
    )
    trade_date = current_time.date().isoformat()
    created_at = current_time.isoformat()

    for db_path in _paper_snapshot_db_paths():
        _ensure_paper_snapshot_tables(db_path)
        conn = _open_sqlite(db_path)
        try:
            if order_side and trade_qty > 0:
                conn.execute(
                    """
                    INSERT INTO orders (symbol, side, quantity, price, amount, status, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (proposal.symbol, order_side, trade_qty, latest_price, amount, 'filled', created_at),
                )
            conn.execute("DELETE FROM positions WHERE symbol = ?", (proposal.symbol,))
            if target_qty > 0:
                conn.execute(
                    """
                    INSERT INTO positions (symbol, quantity, avg_cost, market_value, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (proposal.symbol, target_qty, new_avg_cost, new_position_value, created_at),
                )
            _append_daily_nav_if_needed(
                conn,
                trade_date=trade_date,
                cash=new_cash,
                position_value=new_position_value,
                total_equity=new_total_equity,
            )
            conn.commit()
        finally:
            conn.close()

    _record_paper_execution_audit(
        db,
        proposal=proposal,
        current_time=current_time,
        event_type='paper_execution_cycle',
        payload={
            'reason': reason,
            'signal': signal.value,
            'symbol': proposal.symbol,
            'latest_price': latest_price,
            'latest_price_as_of': latest_price_as_of,
            'price_age_hours': price_age_hours,
            'price_changed': price_changed,
            'equity_changed': equity_changed,
            'rebalance_triggered': trade_qty > 0,
            'explanation_key': explanation_key,
            'explanation': explanation,
            'current_quantity': current_qty,
            'target_quantity': target_qty,
            'order_side': order_side,
            'order_quantity': trade_qty,
            'cash': new_cash,
            'position_value': new_position_value,
            'total_equity': new_total_equity,
        },
    )
    return {
        'executed': True,
        'signal': signal.value,
        'target_quantity': target_qty,
        'order_quantity': trade_qty,
        'order_side': order_side,
        'latest_price': latest_price,
        'latest_price_as_of': latest_price_as_of,
        'price_age_hours': price_age_hours,
        'price_changed': price_changed,
        'equity_changed': equity_changed,
        'rebalance_triggered': trade_qty > 0,
        'explanation_key': explanation_key,
        'explanation': explanation,
        'cash': new_cash,
        'position_value': new_position_value,
        'total_equity': new_total_equity,
    }


def _bootstrap_paper_trade_for_proposal(
    db: Session,
    *,
    proposal: StrategyProposal,
    current_time: datetime,
    decision_id: str | None,
    reason: str,
) -> bool:
    if _paper_trade_already_bootstrapped(proposal.id, db):
        return False

    market_open, market_message = _paper_market_is_open(
        current_time=current_time,
        symbol=proposal.symbol,
        market_scope=proposal.market_scope,
    )
    if not market_open:
        db.add(
            AuditRecord(
                run_id=proposal.run_id,
                decision_id=decision_id or f"paper-trade-skip-{stable_hash([proposal.id, reason, current_time.isoformat()])}",
                event_type='paper_trade_bootstrap_skipped',
                entity_type='paper_runtime',
                entity_id=proposal.id,
                strategy_dsl_hash=stable_hash(proposal.strategy_dsl),
                market_snapshot_hash=proposal.market_snapshot_hash,
                event_digest_hash=proposal.event_digest_hash,
                payload={
                    'symbol': proposal.symbol,
                    'reason': reason,
                    'message': market_message,
                },
                created_at=current_time,
            )
        )
        db.flush()
        return False

    source_manager = get_source_manager()
    if hasattr(source_manager, 'fetch_latest_quote'):
        latest_quote = source_manager.fetch_latest_quote(proposal.symbol)
        latest_price = float(latest_quote['price']) if latest_quote is not None and latest_quote.get('price') is not None else None
        latest_price_as_of = str(latest_quote.get('as_of')) if latest_quote is not None and latest_quote.get('as_of') is not None else None
    else:
        latest_price = source_manager.fetch_latest_price(proposal.symbol)
        latest_price_as_of = None
    if latest_price is None or latest_price <= 0:
        db.add(
            AuditRecord(
                run_id=proposal.run_id,
                decision_id=decision_id or f"paper-trade-skip-{stable_hash([proposal.id, reason, current_time.isoformat()])}",
                event_type='paper_trade_bootstrap_skipped',
                entity_type='paper_runtime',
                entity_id=proposal.id,
                strategy_dsl_hash=stable_hash(proposal.strategy_dsl),
                market_snapshot_hash=proposal.market_snapshot_hash,
                event_digest_hash=proposal.event_digest_hash,
                payload={
                    'symbol': proposal.symbol,
                    'reason': reason,
                    'message': 'latest_price_unavailable',
                    'latest_price_as_of': latest_price_as_of,
                },
                created_at=current_time,
            )
        )
        db.flush()
        return False

    sizing = proposal.strategy_dsl.get('position_sizing', {}) if isinstance(proposal.strategy_dsl, dict) else {}
    sizing_value = float(sizing.get('value', 0.25)) if isinstance(sizing, dict) else 0.25
    sizing_value = max(0.05, min(0.5, sizing_value))
    initial_equity = float(get_settings().portfolio.default_capital)
    target_notional = initial_equity * sizing_value
    lot_size = _market_lot_size(proposal.symbol)
    quantity = int(target_notional // latest_price)
    quantity = max(lot_size, (quantity // lot_size) * lot_size)
    amount = round(quantity * latest_price, 2)
    remaining_cash = round(max(0.0, initial_equity - amount), 2)
    trade_date = current_time.date().isoformat()
    written_paths: list[str] = []

    for db_path in _paper_snapshot_db_paths():
        _ensure_paper_snapshot_tables(db_path)
        conn = _open_sqlite(db_path)
        try:
            created_at = current_time.isoformat()
            conn.execute(
                """
                INSERT INTO orders (symbol, side, quantity, price, amount, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (proposal.symbol, 'buy', quantity, latest_price, amount, 'filled', created_at),
            )
            conn.execute("DELETE FROM positions WHERE symbol = ?", (proposal.symbol,))
            conn.execute(
                """
                INSERT INTO positions (symbol, quantity, avg_cost, market_value, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (proposal.symbol, quantity, latest_price, amount, created_at),
            )
            _append_daily_nav_if_needed(
                conn,
                trade_date=trade_date,
                cash=remaining_cash,
                position_value=amount,
                total_equity=round(remaining_cash + amount, 2),
            )
            conn.commit()
            written_paths.append(db_path)
        finally:
            conn.close()

    db.add(
        AuditRecord(
            run_id=proposal.run_id,
            decision_id=decision_id or f"paper-trade-{stable_hash([proposal.id, reason, current_time.isoformat()])}",
            event_type='paper_trade_bootstrapped',
            entity_type='paper_runtime',
            entity_id=proposal.id,
            strategy_dsl_hash=stable_hash(proposal.strategy_dsl),
            market_snapshot_hash=proposal.market_snapshot_hash,
            event_digest_hash=proposal.event_digest_hash,
            payload={
                'symbol': proposal.symbol,
                'quantity': quantity,
                'price': latest_price,
                'latest_price_as_of': latest_price_as_of,
                'amount': amount,
                'remaining_cash': remaining_cash,
                'trade_date': trade_date,
                'reason': reason,
                'db_paths': written_paths,
            },
            created_at=current_time,
        )
    )
    db.flush()
    return True


def _static_event_scope() -> tuple[str, str]:
    settings = get_settings()
    raw_symbol = settings.portfolio.symbols[0] if settings.portfolio.symbols else "2800.HK"
    market = detect_market(raw_symbol)
    normalized = normalize_symbol(raw_symbol, market=market)
    market_scope = {
        'hk': 'HK',
        'cn': 'CN',
        'us': 'US',
    }.get(market, 'HK')
    return normalized, market_scope


def _static_universe_selection() -> dict[str, object]:
    symbol, market_scope = _static_event_scope()
    benchmark_symbol = get_market_profile(market_scope).benchmark_symbol
    return {
        "mode": get_settings().universe.mode,
        "market_scope": market_scope,
        "selected_symbol": symbol,
        "source": "static",
        "generated_at": now_tz().isoformat(),
        "selection_reason": "Static universe mode keeps the configured benchmark symbol as the research anchor.",
        "top_factors": ["static_anchor"],
        "candidate_count": 1,
        "top_n_limit": 1,
        "min_turnover_millions": None,
        "account_capital_hkd": float(get_settings().portfolio.default_capital),
        "max_lot_cost_ratio": float(get_settings().universe.max_lot_cost_ratio),
        "benchmark_symbol": benchmark_symbol,
        "benchmark_gap": 0.0 if symbol == benchmark_symbol else None,
        "candidates": [
            {
                "rank": 1,
                "symbol": symbol,
                "name": symbol,
                "latest_price": None,
                "change_pct": None,
                "amplitude_pct": None,
                "turnover_millions": None,
                "score": None,
                "factor_scores": {},
                "reason_tags": ["static_anchor"],
                "selection_reason": "Configured benchmark symbol retained because dynamic universe selection is disabled.",
                "source": "static",
            }
        ],
        "benchmark_candidate": {
            "rank": 1,
            "symbol": symbol,
            "name": symbol,
            "latest_price": None,
            "change_pct": None,
            "amplitude_pct": None,
            "return_20d_pct": None,
            "return_60d_pct": None,
            "volatility_20d_pct": None,
            "turnover_millions": None,
            "score": None,
            "factor_scores": {},
            "reason_tags": ["static_anchor"],
            "selection_reason": "Configured benchmark symbol retained because dynamic universe selection is disabled.",
            "source": "static",
        },
    }


def get_universe_selection(db: Session, *, refresh: bool = False, current_time: datetime | None = None) -> dict[str, object]:
    settings = get_settings()
    if settings.universe.mode != "dynamic_hk":
        return _static_universe_selection()

    current_time = current_time or now_tz()
    existing = _get_runtime_setting_json(db, _UNIVERSE_SELECTION_KEY)
    if not refresh and isinstance(existing, dict) and existing.get("selected_symbol"):
        candidates = list(existing.get("candidates", [])) if isinstance(existing.get("candidates"), list) else []
        selected_symbol = str(existing.get("selected_symbol"))
        benchmark_symbol = get_market_profile("HK").benchmark_symbol
        selected_candidate = next(
            (item for item in candidates if str(item.get("symbol")) == selected_symbol),
            candidates[0] if candidates else {},
        )
        benchmark_candidate = next(
            (dict(item) for item in candidates if str(item.get("symbol")) == benchmark_symbol),
            None,
        )
        existing.setdefault("candidate_count", len(candidates))
        existing.setdefault("top_n_limit", int(settings.universe.top_n))
        existing.setdefault("min_turnover_millions", float(settings.universe.min_turnover_millions))
        existing.setdefault("account_capital_hkd", float(settings.portfolio.default_capital))
        existing.setdefault("max_lot_cost_ratio", float(settings.universe.max_lot_cost_ratio))
        existing.setdefault("benchmark_symbol", benchmark_symbol)
        existing.setdefault("benchmark_candidate", benchmark_candidate)
        if existing.get("benchmark_gap") is None and benchmark_candidate is not None:
            selected_score = selected_candidate.get("score")
            benchmark_score = benchmark_candidate.get("score")
            if selected_score is not None and benchmark_score is not None:
                existing["benchmark_gap"] = round(float(selected_score) - float(benchmark_score), 2)
        has_enriched_candidate = bool(selected_candidate.get("selection_reason")) and selected_candidate.get("rank") is not None
        if existing.get("selection_reason") and existing.get("top_factors") and has_enriched_candidate:
            return existing

    previous_symbol = str(existing.get("selected_symbol")) if isinstance(existing, dict) and existing.get("selected_symbol") else None
    try:
        candidates = fetch_hk_universe_candidates(
            top_n=max(1, int(settings.universe.top_n)),
            min_turnover_millions=float(settings.universe.min_turnover_millions),
            account_capital_hkd=float(settings.portfolio.default_capital),
            max_lot_cost_ratio=float(settings.universe.max_lot_cost_ratio),
        )
    except Exception as exc:
        fallback = _static_universe_selection()
        fallback["mode"] = settings.universe.mode
        fallback["source"] = "dynamic_fallback_static"
        fallback["generated_at"] = current_time.isoformat()
        fallback["error"] = str(exc)
        _set_runtime_setting_json(db, _UNIVERSE_SELECTION_KEY, fallback, current_time)
        return fallback
    if not candidates:
        fallback = _static_universe_selection()
        fallback["mode"] = settings.universe.mode
        fallback["source"] = "dynamic_fallback_static"
        fallback["generated_at"] = current_time.isoformat()
        _set_runtime_setting_json(db, _UNIVERSE_SELECTION_KEY, fallback, current_time)
        return fallback

    selected_candidate = dict(candidates[0])
    benchmark_symbol = get_market_profile("HK").benchmark_symbol
    benchmark_candidate = next(
        (dict(item) for item in candidates if str(item.get("symbol")) == benchmark_symbol),
        None,
    )
    payload = {
        "mode": settings.universe.mode,
        "market_scope": "HK",
        "selected_symbol": str(selected_candidate["symbol"]),
        "source": "akshare",
        "generated_at": current_time.isoformat(),
        "selection_reason": str(selected_candidate.get("selection_reason") or "Selected as the strongest current HK candidate."),
        "top_factors": [str(item) for item in list(selected_candidate.get("reason_tags", []))[:4]],
        "candidate_count": len(candidates),
        "top_n_limit": int(settings.universe.top_n),
        "min_turnover_millions": float(settings.universe.min_turnover_millions),
        "account_capital_hkd": float(settings.portfolio.default_capital),
        "max_lot_cost_ratio": float(settings.universe.max_lot_cost_ratio),
        "benchmark_symbol": benchmark_symbol,
        "benchmark_gap": (
            round(float(selected_candidate.get("score", 0.0)) - float(benchmark_candidate.get("score", 0.0)), 2)
            if benchmark_candidate is not None and selected_candidate.get("score") is not None and benchmark_candidate.get("score") is not None
            else None
        ),
        "benchmark_candidate": benchmark_candidate,
        "candidates": candidates,
    }
    _set_runtime_setting_json(db, _UNIVERSE_SELECTION_KEY, payload, current_time)
    top_candidates = [
        {
            "rank": item.get("rank"),
            "symbol": item.get("symbol"),
            "score": item.get("score"),
            "selection_reason": item.get("selection_reason"),
            "reason_tags": item.get("reason_tags", []),
        }
        for item in candidates[:3]
    ]
    _record_system_audit(
        db,
        event_type="universe_selection_evaluated",
        entity_type="universe_selection",
        entity_id="hk_dynamic",
        payload={
            "previous_symbol": previous_symbol,
            "selected_symbol": payload["selected_symbol"],
            "candidate_count": len(candidates),
            "source": "akshare",
            "selection_reason": payload["selection_reason"],
            "top_factors": payload["top_factors"],
            "selected_candidate": {
                "symbol": selected_candidate.get("symbol"),
                "name": selected_candidate.get("name"),
                "score": selected_candidate.get("score"),
                "turnover_millions": selected_candidate.get("turnover_millions"),
                "change_pct": selected_candidate.get("change_pct"),
                "amplitude_pct": selected_candidate.get("amplitude_pct"),
                "factor_scores": selected_candidate.get("factor_scores", {}),
                "reason_tags": selected_candidate.get("reason_tags", []),
                "selection_reason": selected_candidate.get("selection_reason"),
            },
            "top_candidates": top_candidates,
        },
        created_at=current_time,
    )
    if previous_symbol != payload["selected_symbol"]:
        _record_system_audit(
            db,
            event_type="universe_selection_changed",
            entity_type="universe_selection",
            entity_id="hk_dynamic",
            payload={
                "previous_symbol": previous_symbol,
                "selected_symbol": payload["selected_symbol"],
                "candidate_count": len(candidates),
                "source": "akshare",
                "selection_reason": payload["selection_reason"],
                "top_factors": payload["top_factors"],
                "selected_candidate": {
                    "symbol": selected_candidate.get("symbol"),
                    "name": selected_candidate.get("name"),
                    "score": selected_candidate.get("score"),
                    "turnover_millions": selected_candidate.get("turnover_millions"),
                    "change_pct": selected_candidate.get("change_pct"),
                    "amplitude_pct": selected_candidate.get("amplitude_pct"),
                    "factor_scores": selected_candidate.get("factor_scores", {}),
                    "reason_tags": selected_candidate.get("reason_tags", []),
                    "selection_reason": selected_candidate.get("selection_reason"),
                },
                "top_candidates": top_candidates,
            },
            created_at=current_time,
        )
    return payload


def _event_scope(db: Session | None = None, *, refresh: bool = False, current_time: datetime | None = None) -> tuple[str, str]:
    if db is not None:
        selection = get_universe_selection(db, refresh=refresh, current_time=current_time)
        symbol = str(selection.get("selected_symbol") or _static_event_scope()[0])
        market_scope = str(selection.get("market_scope") or "HK")
        return symbol, market_scope
    return _static_event_scope()


def _current_market_profile(market_scope: str) -> dict[str, object]:
    return get_market_profile(market_scope).to_dict()


def _current_strategy_knowledge(market_scope: str) -> list[dict[str, object]]:
    return knowledge_payload_for_market(market_scope)


def _knowledge_preferences_for_market_profile(market_profile: dict[str, object]) -> tuple[list[str], list[str]]:
    return knowledge_preferences_from_market_profile(
        preferred_baseline_tags=list(market_profile.get("preferred_baseline_tags", []) or []),
        discouraged_baseline_tags=list(market_profile.get("discouraged_baseline_tags", []) or []),
    )


def _baseline_family_map_for_market(market_scope: str) -> dict[str, list[str]]:
    market = market_scope.upper()
    mapping: dict[str, list[str]] = {}
    for definition in get_strategy_registry().definitions():
        if market not in definition.supported_markets:
            continue
        mapping[definition.name] = list(definition.knowledge_families)
    mapping["novel_composite"] = []
    return mapping


def _knowledge_entries(family_keys: list[str]) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    seen: set[str] = set()
    for family_key in family_keys:
        if family_key in seen:
            continue
        seen.add(family_key)
        try:
            entries.append(get_strategy_knowledge(family_key).to_dict())
        except KeyError:
            continue
    return entries


def _market_governance_profile(market_scope: str) -> dict[str, float | int]:
    profile = get_market_profile(market_scope)
    governance = profile.governance
    return {
        'promote_threshold': governance.promote_threshold,
        'keep_threshold': governance.keep_threshold,
        'challenger_min_delta': governance.challenger_min_delta,
        'cooldown_days': governance.cooldown_days,
        'live_drawdown_pause': governance.live_drawdown_pause,
        'live_drawdown_rollback': governance.live_drawdown_rollback,
        'acceptance_min_days': governance.acceptance_min_days,
        'acceptance_min_fill_rate': governance.acceptance_min_fill_rate,
        'acceptance_max_drawdown': governance.acceptance_max_drawdown,
    }


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
    symbol_scope, market_scope = _event_scope(db)
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
            fallback_last_success_at = previous_status.get("last_success_at")
            if using_last_known_context:
                fallback_last_success_at = max(seed.published_at for seed in fallback_seeds).isoformat()
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
                "last_success_at": fallback_last_success_at,
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


def purge_out_of_scope_event_history(db: Session, *, market_scope: str) -> None:
    out_of_scope_digests = list(
        db.execute(
            select(DailyEventDigest).where(DailyEventDigest.market_scope != market_scope)
        ).scalars()
    )
    for digest in out_of_scope_digests:
        db.delete(digest)

    out_of_scope_events = list(
        db.execute(
            select(EventRecord).where(EventRecord.market_scope != market_scope)
        ).scalars()
    )
    for record in out_of_scope_events:
        db.delete(record)
    db.flush()


def _latest_digest(db: Session) -> DailyEventDigest:
    symbol_scope, market_scope = _event_scope(db)
    digest = db.execute(
        select(DailyEventDigest)
        .where(
            DailyEventDigest.market_scope == market_scope,
            DailyEventDigest.symbol_scope.in_([symbol_scope, '*']),
        )
        .order_by(DailyEventDigest.trade_date.desc(), DailyEventDigest.id.desc())
        .limit(1)
    ).scalars().first()
    if digest is None:
        sync_event_stream(db)
        sync_daily_event_digests(db)
        digest = db.execute(
            select(DailyEventDigest)
            .where(
                DailyEventDigest.market_scope == market_scope,
                DailyEventDigest.symbol_scope.in_([symbol_scope, '*']),
            )
            .order_by(DailyEventDigest.trade_date.desc(), DailyEventDigest.id.desc())
            .limit(1)
        ).scalars().first()
    if digest is None:
        created_at = now_tz()
        trade_date = created_at.date().isoformat()
        fallback_payload = {
            'trade_date': trade_date,
            'market_scope': market_scope,
            'symbol_scope': symbol_scope,
            'macro_summary': 'No macro events available.',
            'event_scores': {
                'aggregate_sentiment': 0.0,
                'macro_bias': 0.0,
            },
            'event_ids': [],
        }
        digest = DailyEventDigest(
            trade_date=trade_date,
            market_scope=market_scope,
            symbol_scope=symbol_scope,
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
    return get_runtime_state_json(key)


def _set_runtime_setting_json(db: Session, key: str, value_json: dict[str, object], updated_at: datetime) -> None:
    set_runtime_state_json(key, value_json, updated_at=updated_at)


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
    universe_selection = get_universe_selection(db)
    market_profile = _current_market_profile(str(digest.market_scope))
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
        'market_scope': digest.market_scope,
        'regime': regime,
        'confidence': confidence,
        'event_digest_hash': digest.digest_hash,
        'aggregate_sentiment': aggregate_sentiment,
        'reason': reason,
    }
    summary = (
        f"{digest.symbol_scope} ({market_profile['label']}) is in {regime.lower()} mode with confidence {confidence:.2f}. "
        f"Aggregate event sentiment is {aggregate_sentiment:+.2f}; "
        f"macro pulse says '{digest.macro_summary}'."
    )
    base_snapshot = {
        'regime': regime,
        'confidence': confidence,
        'summary': summary,
        'market_snapshot_hash': stable_hash(snapshot_payload),
        'symbol': digest.symbol_scope,
        'market_profile': market_profile,
        'universe_selection': universe_selection,
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
            'knowledge_families_used': ['trend_following'],
            'source_kind': 'mock',
            'provider_status': provider_status.status,
            'provider_model': provider_status.model,
            'provider_message': provider_status.message,
            'thesis': 'Use trend persistence plus macro stability to keep a single active exposure with low turnover.',
            'baseline_delta_summary': '在均线趋势基线上强化宏观稳定性过滤，属于温和的趋势变体。',
            'novelty_claim': '轻度创新：趋势基线 + 宏观稳定性过滤。',
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
            'knowledge_families_used': ['breakout', 'volatility_filter'],
            'source_kind': 'mock',
            'provider_status': provider_status.status,
            'provider_model': provider_status.model,
            'provider_message': provider_status.message,
            'thesis': 'Watch for volatility compression and breakout only when macro drift stays contained.',
            'baseline_delta_summary': '在通道突破上强调波动压缩和宏观平稳约束，属于突破过滤变体。',
            'novelty_claim': '中等创新：突破基线 + 波动率过滤。',
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
            'knowledge_families_used': ['mean_reversion', 'momentum_filter'],
            'source_kind': 'mock',
            'provider_status': provider_status.status,
            'provider_model': provider_status.model,
            'provider_message': provider_status.message,
            'thesis': 'Fade short over-extension if macro pressure eases and realized volatility compresses.',
            'baseline_delta_summary': '在均值回归上加入宏观缓和和波动收缩前提，属于反转过滤变体。',
            'novelty_claim': '轻度创新：均值回归基线 + 环境过滤。',
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
    # Keep each live cycle small so downstream debate/risk stages do not stall the whole runtime.
    for index, proposal in enumerate(proposals[:2]):
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
        knowledge_families_used = [
            str(item)
            for item in list(proposal.get('knowledge_families_used', []) or [])
            if str(item).strip()
        ]
        if not knowledge_families_used and base_strategy != 'novel_composite':
            knowledge_families_used = list(get_strategy_registry().get(base_strategy).knowledge_families)
        if base_strategy == 'novel_composite' and not knowledge_families_used:
            continue
        normalized.append(
            {
                'title': title,
                'base_strategy': base_strategy,
                'thesis': thesis,
                'knowledge_families_used': knowledge_families_used,
                'baseline_delta_summary': str(proposal.get('baseline_delta_summary', '')).strip()[:240],
                'novelty_claim': str(proposal.get('novelty_claim', '')).strip()[:240],
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
        market_profile=dict(snapshot['market_profile']),
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
    market_profile = dict(snapshot['market_profile'])
    strategy_knowledge = _current_strategy_knowledge(str(digest.market_scope))
    knowledge_preferences, knowledge_discouraged = _knowledge_preferences_for_market_profile(market_profile)
    baseline_family_map = _baseline_family_map_for_market(str(digest.market_scope))
    baseline_strategies = [
        {
            'strategy_name': item.strategy_name,
            'default_params': item.default_params,
            'description': item.description,
            'tags': list(definition.tags),
            'supported_markets': list(definition.supported_markets),
            'market_bias': definition.market_bias,
            'knowledge_families': list(definition.knowledge_families),
            'strategy_family_label_zh': definition.strategy_family_label_zh,
            'knowledge_notes_zh': definition.knowledge_notes_zh,
        }
        for item in db.execute(select(StrategySnapshot).order_by(StrategySnapshot.strategy_name.asc())).scalars()
        if (definition := get_strategy_registry().get(item.strategy_name)).supported_markets and str(digest.market_scope) in definition.supported_markets
    ]
    payload = build_strategy_agent_payload(
        symbol=symbol,
        market_scope=str(digest.market_scope),
        timezone=get_settings().timezone,
        market_snapshot={
            'regime': snapshot['regime'],
            'confidence': snapshot['confidence'],
            'summary': snapshot['summary'],
            'price_context': snapshot['price_context'],
            'event_lane_sources': snapshot['event_lane_sources'],
        },
        market_profile=market_profile,
        baseline_strategies=baseline_strategies,
        strategy_knowledge=strategy_knowledge,
        knowledge_preferences=knowledge_preferences,
        knowledge_discouraged=knowledge_discouraged,
        baseline_family_map=baseline_family_map,
        hard_limits=['long_only', 'no_leverage', *list(market_profile.get('execution_constraints', []))],
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
        'source_kind': proposal.source_kind,
        'promoted_at': proposal.promoted_at.isoformat() if proposal.promoted_at else None,
    }


def _cooldown_remaining_days(promoted_at: str | None, current_time: datetime, cooldown_days: int) -> int:
    if not promoted_at:
        return 0
    promoted = datetime.fromisoformat(promoted_at)
    elapsed_days = max(0, (current_time.date() - promoted.date()).days)
    remaining = cooldown_days - elapsed_days
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
    market_scope: str,
    current_time: datetime,
    proposal_source_kind: str = 'mock',
    backtest_gate: dict[str, object] | None = None,
    knowledge_assessment: dict[str, object] | None = None,
) -> tuple[ProposalStatus, RiskDecisionAction, dict[str, object]]:
    settings_governance = get_settings().governance
    market_governance = _market_governance_profile(market_scope)
    blocked_reasons: list[str] = []
    active_score = float(active_context['final_score']) if active_context else None
    score_delta = round(final_score - active_score, 1) if active_score is not None else None
    promoted_at = active_context.get('promoted_at') if active_context else None
    active_source_kind = str(active_context.get('source_kind', 'mock')) if active_context else None
    cooldown_remaining_days = _cooldown_remaining_days(
        str(promoted_at) if promoted_at else None,
        current_time,
        int(market_governance['cooldown_days']),
    )
    replacing_mock_active = (
        active_context is not None
        and active_source_kind == 'mock'
        and proposal_source_kind != 'mock'
        and active_score is not None
        and final_score >= active_score
        and final_score >= float(market_governance['promote_threshold'])
    )
    can_challenge_active = active_context is None or (
        score_delta is not None and score_delta >= float(market_governance['challenger_min_delta']) and cooldown_remaining_days == 0
    )
    if replacing_mock_active:
        can_challenge_active = True

    if not bottom_line_passed:
        blocked_reasons.append('bottom_line_failed')
    if final_score < float(market_governance['keep_threshold']):
        blocked_reasons.append('below_keep_threshold')
    if final_score < float(market_governance['promote_threshold']):
        blocked_reasons.append('below_promote_threshold')
    if active_context and score_delta is not None and score_delta < float(market_governance['challenger_min_delta']) and not replacing_mock_active:
        blocked_reasons.append('delta_below_threshold')
    if cooldown_remaining_days > 0 and not replacing_mock_active:
        blocked_reasons.append('cooldown_active')
    if settings_governance.block_promotion_on_macro_degrade and bool(macro_status.get('degraded')):
        blocked_reasons.append('macro_provider_degraded')
    if settings_governance.require_backtest_before_paper:
        if not isinstance(backtest_gate, dict):
            blocked_reasons.append('backtest_missing')
        elif not bool(backtest_gate.get('eligible_for_paper', False)):
            blocked_reasons.extend(
                [str(item) for item in list(backtest_gate.get('blocked_reasons', []) or [])] or ['backtest_not_passed']
            )
    knowledge_blocked_reasons = []
    if isinstance(knowledge_assessment, dict):
        knowledge_blocked_reasons = [str(item) for item in list(knowledge_assessment.get('blocked_reasons', []) or [])]
        for reason in knowledge_blocked_reasons:
            if reason not in blocked_reasons:
                blocked_reasons.append(reason)

    promote_allowed = (
        bottom_line_passed
        and final_score >= float(market_governance['promote_threshold'])
        and can_challenge_active
        and (
            not settings_governance.require_backtest_before_paper
            or (isinstance(backtest_gate, dict) and bool(backtest_gate.get('eligible_for_paper', False)))
        )
        and not (
            settings_governance.block_promotion_on_macro_degrade and bool(macro_status.get('degraded'))
        )
        and not any(reason in {'knowledge_family_mismatch', 'knowledge_failure_mode_risk', 'knowledge_param_outlier', 'knowledge_low_novelty'} for reason in blocked_reasons)
    )

    if promote_allowed:
        status = ProposalStatus.ACTIVE
        action = RiskDecisionAction.PROMOTE_TO_PAPER
    elif bottom_line_passed and final_score >= float(market_governance['keep_threshold']):
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
            'market_scope': market_scope,
            'promote_threshold': market_governance['promote_threshold'],
            'keep_threshold': market_governance['keep_threshold'],
            'challenger_min_delta': market_governance['challenger_min_delta'],
            'cooldown_days': market_governance['cooldown_days'],
        },
        'promotion_gate': {
            'eligible': action == RiskDecisionAction.PROMOTE_TO_PAPER,
            'blocked_reasons': blocked_reasons,
            'backtest_required': bool(settings_governance.require_backtest_before_paper),
            'backtest_summary': str(backtest_gate.get('summary', '')) if isinstance(backtest_gate, dict) else '',
        },
        'active_comparison': {
            'active_title': active_context.get('title') if active_context else None,
            'active_score': active_score,
            'score_delta': score_delta,
            'can_challenge_active': can_challenge_active,
            'cooldown_remaining_days': cooldown_remaining_days,
            'replacing_mock_active': replacing_mock_active,
        },
        'macro_dependency': {
            'provider': macro_status.get('provider'),
            'status': macro_status.get('status'),
            'degraded': bool(macro_status.get('degraded')),
        },
        'knowledge_gate': {
            'families_used': list(knowledge_assessment.get('knowledge_families_used', [])) if isinstance(knowledge_assessment, dict) else [],
            'fit_assessment': str(knowledge_assessment.get('knowledge_fit_assessment', 'unknown')) if isinstance(knowledge_assessment, dict) else 'unknown',
            'risk_flags': list(knowledge_assessment.get('knowledge_risk_flags', [])) if isinstance(knowledge_assessment, dict) else [],
            'failure_mode_hits': list(knowledge_assessment.get('knowledge_failure_mode_hits', [])) if isinstance(knowledge_assessment, dict) else [],
            'novelty_assessment': str(knowledge_assessment.get('novelty_assessment', 'unknown')) if isinstance(knowledge_assessment, dict) else 'unknown',
            'blocked_reasons': knowledge_blocked_reasons,
        },
        'market_profile': _current_market_profile(market_scope),
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
    market_profile = dict(snapshot.get('market_profile', _current_market_profile(str(digest.market_scope))))
    market_governance = _market_governance_profile(str(digest.market_scope))
    return {
        'thesis': blueprint['thesis'],
        'market_regime_clause': {
            'required_regime': snapshot['regime'],
            'event_digest_hash': digest.digest_hash,
            'market_scope': digest.market_scope,
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
            {'rule': 'market_execution_constraints', 'value': market_profile.get('execution_constraints', [])},
        ],
        'position_sizing': {'mode': 'fixed_fraction', 'value': 0.25},
        'holding_constraints': {'min_holding_days': 5, 'cooldown_days': market_governance['cooldown_days']},
        'features_used': blueprint['features_used'],
        'params': {'base_strategy': base_strategy, 'symbol': digest.symbol_scope, **(params if isinstance(params, dict) else {})},
    }


def _numeric_param_outlier(param_priors: dict[str, dict[str, object]], params: dict[str, object]) -> list[str]:
    hits: list[str] = []
    for key, bounds in param_priors.items():
        value = params.get(key)
        if not isinstance(value, (int, float)):
            continue
        minimum = bounds.get("min")
        maximum = bounds.get("max")
        if isinstance(minimum, (int, float)) and value < minimum:
            hits.append(key)
        elif isinstance(maximum, (int, float)) and value > maximum:
            hits.append(key)
    return hits


def _knowledge_assessment(blueprint: dict[str, object], snapshot: dict[str, object]) -> dict[str, object]:
    market_profile = dict(snapshot.get("market_profile", {}))
    regime = str(snapshot.get("regime", "")).lower()
    base_strategy = str(blueprint.get("base_strategy", ""))
    params = blueprint.get("params", {})
    params = params if isinstance(params, dict) else {}
    families = [str(item) for item in list(blueprint.get("knowledge_families_used", []) or []) if str(item).strip()]
    if not families and base_strategy and base_strategy != "novel_composite":
        try:
            families = list(get_strategy_registry().get(base_strategy).knowledge_families)
        except ValueError:
            families = []

    preferred, discouraged = _knowledge_preferences_for_market_profile(market_profile)
    family_entries = _knowledge_entries(families)
    failure_hits: list[str] = []
    risk_flags: list[str] = []
    param_outliers: list[str] = []
    fit_notes: list[str] = []
    for entry in family_entries:
        risk_flags.extend([str(item) for item in list(entry.get("risk_flags", []) or [])])
        param_outliers.extend(_numeric_param_outlier(dict(entry.get("parameter_priors", {}) or {}), params))
        discouraged_conditions = [str(item).lower() for item in list(entry.get("discouraged_market_conditions", []) or [])]
        preferred_conditions = [str(item).lower() for item in list(entry.get("preferred_market_conditions", []) or [])]
        if regime in discouraged_conditions:
            failure_hits.extend([f"{entry['family_key']}:{regime}"])
        if regime in preferred_conditions:
            fit_notes.append(f"{entry['label_zh']}适配当前 {regime} 环境")

    novelty_assessment = "distinct"
    baseline_delta_summary = str(blueprint.get("baseline_delta_summary", "")).strip()
    novelty_claim = str(blueprint.get("novelty_claim", "")).strip()
    defaults: dict[str, object] = {}
    if base_strategy and base_strategy != "novel_composite":
        try:
            defaults = dict(get_strategy_registry().get(base_strategy).default_params)
        except ValueError:
            defaults = {}
    changed_keys = [key for key, value in params.items() if defaults.get(key) != value]
    if base_strategy != "novel_composite":
        if len(changed_keys) <= 1 and len(families) <= 1:
            novelty_assessment = "low"
        elif len(changed_keys) <= 2:
            novelty_assessment = "moderate"
    elif not families:
        novelty_assessment = "low"

    family_mismatch = bool(families) and all(family in discouraged for family in families) and not any(family in preferred for family in families)
    fit_assessment = "aligned"
    if family_mismatch:
        fit_assessment = "mismatch"
    elif failure_hits or param_outliers:
        fit_assessment = "fragile"
    elif any(family in preferred for family in families):
        fit_assessment = "aligned"
    elif families:
        fit_assessment = "neutral"

    blocked_reasons: list[str] = []
    if family_mismatch:
        blocked_reasons.append("knowledge_family_mismatch")
    if failure_hits:
        blocked_reasons.append("knowledge_failure_mode_risk")
    if param_outliers:
        blocked_reasons.append("knowledge_param_outlier")
    if novelty_assessment == "low":
        blocked_reasons.append("knowledge_low_novelty")

    return {
        "knowledge_families_used": families,
        "knowledge_entries": family_entries,
        "knowledge_fit_assessment": fit_assessment,
        "knowledge_risk_flags": sorted(set(risk_flags)),
        "knowledge_failure_mode_hits": failure_hits,
        "novelty_assessment": novelty_assessment,
        "baseline_delta_summary": baseline_delta_summary
        or ("轻微变体，主要沿用既有基线逻辑。" if novelty_assessment == "low" else "在现有基线之上做了市场适配变形。"),
        "novelty_claim": novelty_claim
        or ("轻微变体" if novelty_assessment == "low" else "市场适配型变体"),
        "blocked_reasons": blocked_reasons,
        "fit_notes": fit_notes,
        "param_outliers": sorted(set(param_outliers)),
        "preferred_families": preferred,
        "discouraged_families": discouraged,
    }


def _knowledge_penalty_score(assessment: dict[str, object]) -> float:
    penalty = 0.0
    blocked = set(str(item) for item in list(assessment.get("blocked_reasons", []) or []))
    if "knowledge_family_mismatch" in blocked:
        penalty += 8.0
    if "knowledge_failure_mode_risk" in blocked:
        penalty += 5.0
    if "knowledge_param_outlier" in blocked:
        penalty += 4.0
    if "knowledge_low_novelty" in blocked:
        penalty += 2.0
    return penalty


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
    knowledge_assessment = _knowledge_assessment(blueprint, snapshot)
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
        market_profile=dict(snapshot['market_profile']),
        event_digest={
            'macro_summary': digest.macro_summary,
            'event_scores': digest.event_scores,
        },
        knowledge_context={
            'families_used': knowledge_assessment['knowledge_families_used'],
            'fit_assessment': knowledge_assessment['knowledge_fit_assessment'],
            'failure_mode_hits': knowledge_assessment['knowledge_failure_mode_hits'],
            'baseline_delta_summary': knowledge_assessment['baseline_delta_summary'],
            'novelty_claim': knowledge_assessment['novelty_claim'],
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
        'backtest_admission': True,
    }
    return {
        'bottom_line_report': bottom_line_report,
        'deterministic_evidence': deterministic_evidence,
        'governance_report': governance_report,
        'knowledge_families_used': list(blueprint.get('knowledge_families_used', []) or []),
        'baseline_delta_summary': str(blueprint.get('baseline_delta_summary', '')),
        'novelty_claim': str(blueprint.get('novelty_claim', '')),
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
    backtest_gate = dict(evidence_pack.get('backtest_gate', {}))
    knowledge_context = dict(evidence_pack.get('knowledge_context', {}))
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
        'backtest_gate': {
            'available': bool(backtest_gate.get('available', False)),
            'eligible_for_paper': bool(backtest_gate.get('eligible_for_paper', False)),
            'blocked_reasons': [str(item) for item in list(backtest_gate.get('blocked_reasons', []) or [])],
            'summary': str(backtest_gate.get('summary', '')),
            'review': dict(backtest_gate.get('review', {}) or {}),
            'metrics': dict(backtest_gate.get('metrics', {}) or {}),
            'window': dict(backtest_gate.get('window', {}) or {}),
        },
        'knowledge_fit_assessment': str(knowledge_context.get('knowledge_fit_assessment', 'unknown')),
        'knowledge_risk_flags': [str(item) for item in list(knowledge_context.get('knowledge_risk_flags', []) or [])],
        'knowledge_failure_mode_hits': [str(item) for item in list(knowledge_context.get('knowledge_failure_mode_hits', []) or [])],
        'knowledge_families_used': [str(item) for item in list(knowledge_context.get('knowledge_families_used', []) or [])],
        'baseline_delta_summary': str(knowledge_context.get('baseline_delta_summary', evidence_pack.get('baseline_delta_summary', ''))),
        'verdict': {
            'quality_band': quality_band,
            'comparable': comparable,
            'replaceable': replaceable,
            'accumulable': comparable and oos_passed and robustness_passed,
            'novelty_assessment': str(knowledge_context.get('novelty_assessment', 'unknown')),
        },
    }


def _proposal_base_strategy(proposal: StrategyProposal) -> str:
    return _proposal_base_strategy_from_spec(proposal.title, proposal.strategy_dsl)


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


def _backfill_knowledge_payload(
    evidence_pack: dict[str, object],
    *,
    strategy_dsl: dict[str, object] | None = None,
) -> dict[str, object]:
    if evidence_pack.get('knowledge_context') and evidence_pack.get('knowledge_families_used'):
        return evidence_pack
    dsl = strategy_dsl if isinstance(strategy_dsl, dict) else {}
    params = dict(dsl.get('params', {}) or {}) if isinstance(dsl.get('params', {}), dict) else {}
    base_strategy = str(params.get('base_strategy', '') or '')
    if not base_strategy or base_strategy == 'novel_composite':
        return evidence_pack
    try:
        definition = get_strategy_registry().get(base_strategy)
    except ValueError:
        return evidence_pack
    knowledge_assessment = _knowledge_assessment(
        {
            'base_strategy': base_strategy,
            'params': {key: value for key, value in params.items() if key != 'base_strategy'},
            'knowledge_families_used': list(definition.knowledge_families),
            'baseline_delta_summary': definition.knowledge_notes_zh,
            'novelty_claim': '基线策略',
        },
        {'market_profile': _current_market_profile('HK'), 'regime': ''},
    )
    return {
        **evidence_pack,
        'knowledge_families_used': list(definition.knowledge_families),
        'baseline_delta_summary': definition.knowledge_notes_zh,
        'novelty_claim': str(evidence_pack.get('novelty_claim', '基线策略')),
        'knowledge_context': knowledge_assessment,
    }


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
        quality_report = dict(evidence_pack.get('quality_report', {}) or {})
        if 'backtest_gate' not in quality_report:
            quality_report['backtest_gate'] = {
                'available': False,
                'eligible_for_paper': False,
                'blocked_reasons': ['backtest_not_recorded'],
                'summary': 'Backtest admission was not recorded for this historical proposal.',
                'review': {},
                'metrics': {},
                'window': {},
            }
        quality_report.setdefault('knowledge_fit_assessment', 'unknown')
        quality_report.setdefault('knowledge_risk_flags', [])
        quality_report.setdefault('knowledge_failure_mode_hits', [])
        quality_report.setdefault('knowledge_families_used', list(evidence_pack.get('knowledge_families_used', []) or []))
        quality_report.setdefault('baseline_delta_summary', str(evidence_pack.get('baseline_delta_summary', '')))
        verdict = dict(quality_report.get('verdict', {}) or {})
        verdict.setdefault('novelty_assessment', 'unknown')
        quality_report['verdict'] = verdict
        evidence_pack['quality_report'] = quality_report
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
        proposal.evidence_pack = _ensure_quality_report_payload(
            _backfill_knowledge_payload(dict(proposal.evidence_pack), strategy_dsl=proposal.strategy_dsl),
            proposal.final_score,
        )
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
    market_scope: str,
    current_time: datetime,
) -> dict[str, object]:
    governance = _market_governance_profile(market_scope)
    live_drawdown = _paper_nav_drawdown(nav_rows)
    fill_rate = _order_fill_rate(orders)
    promoted_at = proposal.promoted_at if proposal else None
    live_days = max(0, (current_time.date() - promoted_at.date()).days) if promoted_at else 0
    checks = {
        'minimum_live_days': live_days >= int(governance['acceptance_min_days']),
        'fill_rate_ok': fill_rate is None or fill_rate >= float(governance['acceptance_min_fill_rate']),
        'drawdown_within_acceptance': live_drawdown < float(governance['acceptance_max_drawdown']),
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
    operational_score -= min(0.35, live_drawdown / max(float(governance['acceptance_max_drawdown']), 0.0001) * 0.25)
    if fill_rate is not None:
        operational_score -= max(0.0, float(governance['acceptance_min_fill_rate']) - fill_rate) * 0.5
    operational_score -= pause_events_30d * 0.08
    operational_score -= rollback_events_30d * 0.15
    if bool(macro_status.get('degraded')):
        operational_score -= 0.12
    return {
        'status': status,
        'accepted': status == 'accepted',
        'live_days': live_days,
        'minimum_live_days': governance['acceptance_min_days'],
        'fill_rate': round(fill_rate, 3) if fill_rate is not None else None,
        'minimum_fill_rate': governance['acceptance_min_fill_rate'],
        'drawdown': round(live_drawdown, 4),
        'maximum_acceptance_drawdown': governance['acceptance_max_drawdown'],
        'failed_checks': failed_checks,
        'latest_action': latest_decision.action.value if latest_decision else None,
        'pause_events_30d': pause_events_30d,
        'rollback_events_30d': rollback_events_30d,
        'incident_free_days': incident_free_days,
        'operational_score': round(max(0.0, min(1.0, operational_score)), 2),
        'market_scope': market_scope,
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
        market_scope=str(snapshot['event_digest'].market_scope),
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
            'verdict': verdict,
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


def build_live_readiness(db: Session, *, window_days: int = 30) -> dict[str, object]:
    acceptance = build_acceptance_report(db, window_days=window_days)
    provider_comparison = build_provider_migration_summary(db, window_days=window_days)
    quality = dict(acceptance.get('quality', {}))
    operations = dict(acceptance.get('operations', {}))
    macro = dict(acceptance.get('macro', {}))
    governance = dict(acceptance.get('governance', {}))
    verdict = dict(quality.get('verdict', {}))
    track_record = dict(quality.get('track_record', {}))
    oos_validation = dict(quality.get('oos_validation', {}))

    blockers: list[str] = []
    next_actions: list[str] = []

    quality_score = 30
    if track_record.get('trend') == 'weakening':
        quality_score -= 8
        blockers.append('quality_trend_weakening')
    if not bool(oos_validation.get('passed', False)):
        quality_score -= 8
        blockers.append('oos_validation_not_passed')
    if not bool(verdict.get('replaceable', False)):
        quality_score -= 6
        blockers.append('not_consistently_replaceable')
    if int(track_record.get('stable_streak', 0) or 0) < 20:
        quality_score -= 8
        blockers.append('stable_streak_too_short')
    if float(track_record.get('replaceable_ratio', 0.0) or 0.0) < 0.6:
        quality_score -= 5
        blockers.append('replaceable_ratio_below_threshold')
    quality_score = max(0, quality_score)

    operations_score = 25
    if operations.get('status') != 'accepted':
        operations_score -= 8
        blockers.append('paper_acceptance_not_accepted')
    if int(operations.get('live_days', 0) or 0) < 20:
        operations_score -= 7
        blockers.append('paper_live_days_below_threshold')
    if int(operations.get('rollback_events_30d', 0) or 0) > 0:
        operations_score -= 10
        blockers.append('rollback_seen_in_30d')
    if int(operations.get('pause_events_30d', 0) or 0) > 2:
        operations_score -= 5
        blockers.append('too_many_pause_events')
    if float(operations.get('operational_score', 0.0) or 0.0) < 0.75:
        operations_score -= 5
        blockers.append('operational_score_below_threshold')
    operations_score = max(0, operations_score)

    runtime_score = 25
    if str(acceptance.get('status')) == 'attention':
        runtime_score -= 8
    if str(macro.get('status')) == 'degraded':
        runtime_score -= 7
        blockers.append('macro_pipeline_degraded')
    if float(macro.get('health_score_30d', 0.0) or 0.0) < 0.8:
        runtime_score -= 5
        blockers.append('macro_health_history_too_weak')
    if int(governance.get('fallback_events_30d', 0) or 0) > 3:
        runtime_score -= 5
        blockers.append('too_many_fallback_events')
    runtime_score = max(0, runtime_score)

    explainability_score = 20
    if not governance.get('phase'):
        explainability_score -= 5
        blockers.append('governance_phase_missing')
    if not governance.get('next_step'):
        explainability_score -= 4
        blockers.append('governance_next_step_missing')
    if not isinstance(governance.get('resume_conditions', []), list):
        explainability_score -= 4
        blockers.append('resume_conditions_missing')
    if not acceptance.get('strategy_title'):
        explainability_score -= 7
        blockers.append('no_active_strategy')
    explainability_score = max(0, explainability_score)

    score = quality_score + operations_score + runtime_score + explainability_score
    if score >= 85 and not blockers:
        status = 'ready_candidate'
    elif score >= 65:
        status = 'paper_building_evidence'
    else:
        status = 'not_ready'

    if 'paper_live_days_below_threshold' in blockers:
        next_actions.append('accumulate_more_paper_days')
    if 'stable_streak_too_short' in blockers or 'replaceable_ratio_below_threshold' in blockers:
        next_actions.append('accumulate_longer_quality_history')
    if 'macro_pipeline_degraded' in blockers or 'macro_health_history_too_weak' in blockers:
        next_actions.append('stabilize_macro_pipeline')
    if 'rollback_seen_in_30d' in blockers or 'too_many_pause_events' in blockers:
        next_actions.append('reduce_operational_incidents')
    if not next_actions:
        next_actions.append('keep_collecting_evidence')

    if status == 'ready_candidate':
        summary = 'Live candidate is eligible for human review.'
    elif status == 'paper_building_evidence':
        summary = 'Paper evidence is improving but still below live admission thresholds.'
    else:
        summary = 'System should remain in paper mode until quality, operations, and runtime evidence improve.'

    return {
        'status': status,
        'score': score,
        'summary': summary,
        'approved_for_live': False,
        'blockers': blockers,
        'next_actions': next_actions,
        'dimensions': {
            'quality': quality_score,
            'operations': operations_score,
            'runtime': runtime_score,
            'explainability': explainability_score,
        },
        'evidence': {
            'window_days': window_days,
            'strategy_title': acceptance.get('strategy_title'),
            'quality_trend': track_record.get('trend'),
            'stable_streak': track_record.get('stable_streak'),
            'replaceable_ratio': track_record.get('replaceable_ratio'),
            'oos_passed': oos_validation.get('passed'),
            'live_days': operations.get('live_days'),
            'operational_status': operations.get('status'),
            'operational_score': operations.get('operational_score'),
            'macro_status': macro.get('status'),
            'macro_health_score_30d': macro.get('health_score_30d'),
            'fallback_events_30d': governance.get('fallback_events_30d'),
            'governance_phase': governance.get('phase'),
            'provider_comparison': provider_comparison,
        },
    }


def build_live_readiness_history(db: Session, *, limit: int = 8) -> list[dict[str, object]]:
    rows = list(
        db.execute(
            select(AuditRecord)
            .where(AuditRecord.event_type == 'live_readiness_evaluated')
            .order_by(AuditRecord.created_at.desc(), AuditRecord.id.desc())
            .limit(limit)
        ).scalars()
    )
    history: list[dict[str, object]] = []
    for audit in rows:
        payload = dict(audit.payload or {})
        dimensions = {str(key): int(value) for key, value in dict(payload.get('dimensions', {}) or {}).items()}
        history.append({
            'status': str(payload.get('status', 'not_ready')),
            'score': int(payload.get('score', 0) or 0),
            'summary': str(payload.get('summary', '')),
            'approved_for_live': bool(payload.get('approved_for_live', False)),
            'blockers': [str(item) for item in list(payload.get('blockers', []) or [])],
            'next_actions': [str(item) for item in list(payload.get('next_actions', []) or [])],
            'dimensions': dimensions,
            'evidence': dict(payload.get('evidence', {}) or {}),
            'created_at': audit.created_at,
        })
    return history


def build_live_readiness_change(db: Session, history: list[dict[str, object]] | None = None) -> dict[str, object] | None:
    history = history or build_live_readiness_history(db, limit=8)
    if len(history) < 2:
        return None
    latest = history[0]
    previous = history[1]
    latest_blockers = {str(item) for item in list(latest.get('blockers', []) or [])}
    previous_blockers = {str(item) for item in list(previous.get('blockers', []) or [])}
    score_delta = float(latest.get('score', 0) or 0) - float(previous.get('score', 0) or 0)
    trend = 'improved' if score_delta > 0 else 'weakened' if score_delta < 0 else 'flat'

    linked_changes: list[str] = []
    previous_created_at = previous.get('created_at')
    latest_created_at = latest.get('created_at')
    if isinstance(previous_created_at, datetime) and isinstance(latest_created_at, datetime):
        events = list(
            db.execute(
                select(AuditRecord)
                .where(
                    AuditRecord.created_at > previous_created_at,
                    AuditRecord.created_at <= latest_created_at,
                    AuditRecord.event_type.in_([
                        'universe_selection_changed',
                        'llm_provider_switched',
                        'provider_cohort_started',
                        'provider_comparison_window_closed',
                        'macro_provider_degraded',
                        'macro_provider_recovered',
                        'proposal_created',
                        'risk_decision_recorded',
                    ]),
                )
                .order_by(AuditRecord.created_at.desc(), AuditRecord.id.desc())
                .limit(10)
            ).scalars()
        )
        for event in events:
            payload = dict(event.payload or {})
            if event.event_type == 'universe_selection_changed':
                linked_changes.append(f"Universe shifted to {payload.get('selected_symbol', event.entity_id)}.")
            elif event.event_type == 'llm_provider_switched':
                linked_changes.append(
                    f"LLM provider switched from {payload.get('old_provider', 'unknown')} to {payload.get('new_provider', event.entity_id)}."
                )
            elif event.event_type == 'provider_cohort_started':
                linked_changes.append(f"Started a new provider cohort on {payload.get('cohort_provider', event.entity_id)}.")
            elif event.event_type == 'provider_comparison_window_closed':
                linked_changes.append(
                    f"Closed the previous provider comparison window for {payload.get('provider', event.entity_id)}."
                )
            elif event.event_type == 'macro_provider_degraded':
                linked_changes.append('Macro pipeline degraded and entered fallback handling.')
            elif event.event_type == 'macro_provider_recovered':
                linked_changes.append('Macro pipeline recovered to a healthier provider state.')
            elif event.event_type == 'proposal_created':
                linked_changes.append(f"A new proposal was created: {event.entity_id}.")
            elif event.event_type == 'risk_decision_recorded':
                linked_changes.append(f"A new risk decision was recorded for {event.entity_id}.")
        deduped: list[str] = []
        seen: set[str] = set()
        for item in linked_changes:
            if item in seen:
                continue
            seen.add(item)
            deduped.append(item)
        linked_changes = deduped[:4]

    return {
        'trend': trend,
        'score_delta': round(score_delta, 1),
        'added_blockers': sorted(latest_blockers - previous_blockers),
        'cleared_blockers': sorted(previous_blockers - latest_blockers),
        'linked_changes': linked_changes,
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
    knowledge_assessment = _knowledge_assessment(blueprint, snapshot)
    evidence_pack['knowledge_context'] = knowledge_assessment
    if blueprint.get('source_kind') == 'mock':
        judgment = _fallback_risk_judgment(blueprint)
        evidence_pack['llm_judgment_inputs']['prompt_versions'] = blueprint.get('prompt_versions', {})
        judgment['llm_score'] = max(50.0, judgment['llm_score'] - _knowledge_penalty_score(knowledge_assessment))
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
        market_profile=dict(snapshot['market_profile']),
        event_digest={
            'macro_summary': digest.macro_summary,
            'event_scores': digest.event_scores,
        },
        knowledge_context={
            'families_used': knowledge_assessment['knowledge_families_used'],
            'fit_assessment': knowledge_assessment['knowledge_fit_assessment'],
            'failure_mode_hits': knowledge_assessment['knowledge_failure_mode_hits'],
            'baseline_delta_summary': knowledge_assessment['baseline_delta_summary'],
            'novelty_claim': knowledge_assessment['novelty_claim'],
            'risk_flags': knowledge_assessment['knowledge_risk_flags'],
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
    adjusted_score = max(50.0, min(95.0, llm_score - _knowledge_penalty_score(knowledge_assessment)))
    judgment = {
        'llm_score': adjusted_score,
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

    market_scope = str(snapshot['event_digest'].market_scope)
    governance = _market_governance_profile(market_scope)
    latest_decision = _latest_proposal_decision(active)
    _initialize_paper_snapshot_for_proposal(
        db,
        proposal=active,
        current_time=current_time,
        decision_id=latest_decision.decision_id if latest_decision else None,
        reason='active_backfill',
    )
    _bootstrap_paper_trade_for_proposal(
        db,
        proposal=active,
        current_time=current_time,
        decision_id=latest_decision.decision_id if latest_decision else None,
        reason='active_backfill',
    )
    execute_active_paper_cycle(
        db,
        proposal=active,
        current_time=current_time,
        reason='active_health_check',
    )
    nav_rows = fetch_paper_data(limit=120)['nav']
    paper = fetch_paper_data(limit=120)
    nav_rows = paper['nav']
    orders = paper['orders']
    live_drawdown = _paper_nav_drawdown(nav_rows)
    macro_status = dict(snapshot.get('macro_status', {}))
    operational_acceptance = build_operational_acceptance(
        proposal=active,
        latest_decision=latest_decision,
        nav_rows=nav_rows,
        orders=orders,
        macro_status=macro_status,
        market_scope=str(snapshot['event_digest'].market_scope),
        current_time=current_time,
    )
    if latest_decision and latest_decision.action in {RiskDecisionAction.PAUSE_ACTIVE, RiskDecisionAction.ROLLBACK_TO_PREVIOUS_STABLE}:
        return latest_decision

    if live_drawdown < float(governance['live_drawdown_pause']):
        return None

    previous_stable = _get_previous_stable_strategy(db, exclude_proposal_id=active.id)
    governance_report = {
        'version': 'v1.5',
        'active_health': {
            'live_drawdown': live_drawdown,
            'pause_threshold': governance['live_drawdown_pause'],
            'rollback_threshold': governance['live_drawdown_rollback'],
            'macro_status': macro_status,
            'previous_stable_title': previous_stable.title if previous_stable else None,
            'operational_acceptance': operational_acceptance,
            'market_scope': market_scope,
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
        f"{float(governance['live_drawdown_pause']):.2%}. The active strategy is paused pending review."
    )
    if live_drawdown >= float(governance['live_drawdown_rollback']) and previous_stable is not None:
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
            f"{float(governance['live_drawdown_rollback']):.2%}. Rolling back to {previous_stable.title}."
        )
    elif live_drawdown >= float(governance['live_drawdown_pause']):
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


def _promote_existing_real_candidate_over_mock_active(
    db: Session,
    *,
    active: StrategyProposal,
    current_time: datetime,
) -> StrategyProposal | None:
    if active.source_kind == 'minimax':
        return None
    market_scope = active.market_scope
    governance = _market_governance_profile(market_scope)
    challenger = db.execute(
        select(StrategyProposal)
        .options(selectinload(StrategyProposal.decisions))
        .where(
            StrategyProposal.status == ProposalStatus.CANDIDATE,
            StrategyProposal.symbol == active.symbol,
            StrategyProposal.market_scope == active.market_scope,
            StrategyProposal.source_kind != 'mock',
            StrategyProposal.provider_status == 'ready',
            StrategyProposal.final_score >= float(governance['promote_threshold']),
            StrategyProposal.final_score >= active.final_score,
        )
        .order_by(StrategyProposal.final_score.desc(), StrategyProposal.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if challenger is None:
        return None

    active.status = ProposalStatus.ARCHIVED
    active.archived_at = current_time
    active.updated_at = current_time
    challenger.status = ProposalStatus.ACTIVE
    challenger.promoted_at = current_time
    challenger.updated_at = current_time
    evidence_pack = dict(challenger.evidence_pack or {})
    governance_report = dict(evidence_pack.get('governance_report', {}))
    governance_report['selected_action'] = RiskDecisionAction.PROMOTE_TO_PAPER.value
    active_comparison = dict(governance_report.get('active_comparison', {}))
    active_comparison['active_title'] = active.title
    active_comparison['active_score'] = active.final_score
    active_comparison['score_delta'] = round(challenger.final_score - active.final_score, 1)
    active_comparison['replacing_mock_active'] = True
    governance_report['active_comparison'] = active_comparison
    lifecycle = dict(governance_report.get('lifecycle', {}))
    lifecycle['phase'] = 'promotion_ready'
    lifecycle['next_step'] = 'promote_now'
    governance_report['lifecycle'] = lifecycle
    evidence_pack['governance_report'] = governance_report
    decision = RiskDecision(
        decision_id=f"decision-{stable_hash([challenger.run_id, 'replace_mock_active', current_time.isoformat()])}",
        run_id=challenger.run_id,
        proposal_id=challenger.id,
        action=RiskDecisionAction.PROMOTE_TO_PAPER,
        deterministic_score=challenger.deterministic_score,
        llm_score=challenger.llm_score,
        final_score=challenger.final_score,
        bottom_line_passed=True,
        bottom_line_report=dict(evidence_pack.get('bottom_line_report', {})),
        llm_explanation='Promoted a ready MiniMax HK candidate over legacy mock active strategy.',
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
        payload=_audit_payload(challenger, decision),
        created_at=current_time,
        run_id=challenger.run_id,
        decision_id=decision.decision_id,
        market_snapshot_hash=challenger.market_snapshot_hash,
        event_digest_hash=challenger.event_digest_hash,
    )
    _initialize_paper_snapshot_for_proposal(
        db,
        proposal=challenger,
        current_time=current_time,
        decision_id=decision.decision_id,
        reason='replace_mock_active',
    )
    _bootstrap_paper_trade_for_proposal(
        db,
        proposal=challenger,
        current_time=current_time,
        decision_id=decision.decision_id,
        reason='replace_mock_active',
    )
    return challenger


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
    settings_governance = get_settings().governance
    replacement_promoted = False
    for index, blueprint in enumerate(blueprints):
        deterministic_score = _deterministic_score(index, snapshot, digest, list(blueprint['features_used']))
        provisional_bottom_line = deterministic_score <= 100.0
        knowledge_assessment = _knowledge_assessment(blueprint, snapshot)
        status, action, governance_report = _governance_action(
            final_score=deterministic_score,
            bottom_line_passed=provisional_bottom_line,
            active_context=active_context,
            macro_status=macro_status,
            market_scope=str(digest.market_scope),
            current_time=current_time,
            proposal_source_kind=str(blueprint.get('source_kind', 'mock')),
            backtest_gate=None,
            knowledge_assessment=knowledge_assessment,
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
        dsl = _strategy_dsl(blueprint, snapshot, digest)
        backtest_gate = _proposal_backtest_gate(
            title=str(blueprint['title']),
            symbol=str(snapshot['symbol']),
            strategy_dsl=dsl,
            current_time=current_time,
        )
        evidence_pack['backtest_gate'] = backtest_gate
        evidence_pack['deterministic_evidence'] = {
            **dict(evidence_pack.get('deterministic_evidence', {}) or {}),
            **_backtest_metrics_for_evidence(backtest_gate),
        }
        if settings_governance.require_backtest_before_paper:
            evidence_pack['bottom_line_report'] = {
                **dict(evidence_pack.get('bottom_line_report', {}) or {}),
                'backtest_admission': _backtest_gate_bottom_line(backtest_gate),
            }
        bottom_line_passed = all(bool(value) for value in evidence_pack['bottom_line_report'].values())
        status, action, governance_report = _governance_action(
            final_score=final_score,
            bottom_line_passed=bottom_line_passed,
            active_context=active_context,
            macro_status=macro_status,
            market_scope=str(digest.market_scope),
            current_time=current_time,
            proposal_source_kind=str(blueprint.get('source_kind', 'mock')),
            backtest_gate=backtest_gate,
            knowledge_assessment=knowledge_assessment,
        )
        evidence_pack['governance_report'] = governance_report
        evidence_pack['quality_report'] = _build_quality_report(
            evidence_pack=evidence_pack,
            governance_report=governance_report,
            final_score=final_score,
        )
        proposal = StrategyProposal(
            run_id=f"run-{stable_hash([blueprint['title'], digest.digest_hash, current_time.isoformat(), blueprint.get('source_kind', 'mock')])}",
            title=str(blueprint['title']),
            symbol=str(snapshot['symbol']),
            market_scope=str(digest.market_scope),
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
        db.add(
            AuditRecord(
                run_id=proposal.run_id,
                decision_id=decision.decision_id,
                event_type='strategy_knowledge_applied',
                entity_type='strategy_proposal',
                entity_id=proposal.id,
                strategy_dsl_hash=stable_hash(dsl),
                market_snapshot_hash=proposal.market_snapshot_hash,
                event_digest_hash=proposal.event_digest_hash,
                payload={
                    'knowledge_families_used': list(evidence_pack.get('knowledge_families_used', []) or []),
                    'baseline_delta_summary': str(evidence_pack.get('baseline_delta_summary', '')),
                    'knowledge_fit_assessment': str(dict(evidence_pack.get('knowledge_context', {}) or {}).get('knowledge_fit_assessment', 'unknown')),
                    'knowledge_risk_flags': list(dict(evidence_pack.get('knowledge_context', {}) or {}).get('knowledge_risk_flags', []) or []),
                },
                created_at=current_time,
            )
        )
        db.add(
            AuditRecord(
                run_id=proposal.run_id,
                decision_id=decision.decision_id,
                event_type='strategy_novelty_reviewed',
                entity_type='risk_decision',
                entity_id=decision.id,
                strategy_dsl_hash=stable_hash(dsl),
                market_snapshot_hash=proposal.market_snapshot_hash,
                event_digest_hash=proposal.event_digest_hash,
                payload={
                    'novelty_assessment': str(dict(evidence_pack.get('knowledge_context', {}) or {}).get('novelty_assessment', 'unknown')),
                    'blocked_reasons': list(dict(evidence_pack.get('knowledge_context', {}) or {}).get('blocked_reasons', []) or []),
                    'novelty_claim': str(evidence_pack.get('novelty_claim', '')),
                },
                created_at=current_time,
            )
        )
        if proposal.status == ProposalStatus.ACTIVE:
            _initialize_paper_snapshot_for_proposal(
                db,
                proposal=proposal,
                current_time=current_time,
                decision_id=decision.decision_id,
                reason='promoted_to_paper',
            )
            _bootstrap_paper_trade_for_proposal(
                db,
                proposal=proposal,
                current_time=current_time,
                decision_id=decision.decision_id,
                reason='promoted_to_paper',
            )
            replacement_promoted = True
            active_context = _proposal_context(proposal)
    if replacement_promoted and previous_active is not None:
        previous_active.status = ProposalStatus.ARCHIVED
        previous_active.archived_at = current_time
        previous_active.updated_at = current_time
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


def archive_non_active_strategy_proposals(db: Session, archived_at: datetime) -> None:
    records = list(
        db.execute(
            select(StrategyProposal).where(
                StrategyProposal.status.not_in([ProposalStatus.ARCHIVED, ProposalStatus.ACTIVE])
            )
        ).scalars()
    )
    for record in records:
        record.status = ProposalStatus.ARCHIVED
        record.archived_at = archived_at
        record.updated_at = archived_at
    db.flush()


def archive_out_of_scope_strategy_proposals(
    db: Session,
    *,
    active_symbol: str,
    active_market_scope: str,
    archived_at: datetime,
) -> None:
    records = list(
        db.execute(
            select(StrategyProposal).where(
                StrategyProposal.status != ProposalStatus.ARCHIVED,
                (StrategyProposal.symbol != active_symbol) | (StrategyProposal.market_scope != active_market_scope),
            )
        ).scalars()
    )
    for record in records:
        record.status = ProposalStatus.ARCHIVED
        record.archived_at = archived_at
        record.updated_at = archived_at
    db.flush()


def _proposal_lifecycle_phase(proposal: StrategyProposal) -> str | None:
    latest_decision = _latest_proposal_decision(proposal)
    if latest_decision is None or not isinstance(latest_decision.evidence_pack, dict):
        return None
    return str(
        dict(dict(latest_decision.evidence_pack).get('governance_report', {}))
        .get('lifecycle', {})
        .get('phase')
        or ''
    ) or None


def prune_strategy_proposals(
    db: Session,
    *,
    active_symbol: str,
    active_market_scope: str,
    current_time: datetime,
) -> dict[str, int]:
    settings = get_settings().governance
    archived = {
        'rejected_retention': 0,
        'aged_candidates': 0,
        'overflow_candidates': 0,
    }
    rejected_cutoff = current_time - timedelta(days=max(0, int(settings.rejected_retention_days)))
    rejected_records = list(
        db.execute(
            select(StrategyProposal).where(
                StrategyProposal.status == ProposalStatus.REJECTED,
                StrategyProposal.created_at < rejected_cutoff,
                StrategyProposal.status != ProposalStatus.ARCHIVED,
            )
        ).scalars()
    )
    for record in rejected_records:
        record.status = ProposalStatus.ARCHIVED
        record.archived_at = current_time
        record.updated_at = current_time
        archived['rejected_retention'] += 1

    candidate_records = list(
        db.execute(
            select(StrategyProposal)
            .options(selectinload(StrategyProposal.decisions))
            .where(
                StrategyProposal.status == ProposalStatus.CANDIDATE,
                StrategyProposal.symbol == active_symbol,
                StrategyProposal.market_scope == active_market_scope,
            )
        ).scalars()
    )
    protected_phases = {'candidate_cooldown', 'paused_pending_review'}
    max_age_days = max(1, int(settings.candidate_max_age_days))
    retention_limit = max(1, int(settings.candidate_retention_limit))
    survivors: list[StrategyProposal] = []
    for record in candidate_records:
        phase = _proposal_lifecycle_phase(record)
        age_days = max(0, (current_time.date() - record.created_at.date()).days)
        if age_days > max_age_days and phase not in protected_phases:
            record.status = ProposalStatus.ARCHIVED
            record.archived_at = current_time
            record.updated_at = current_time
            archived['aged_candidates'] += 1
            continue
        survivors.append(record)

    ranked = sorted(survivors, key=lambda item: (item.final_score, item.created_at), reverse=True)
    kept_ids = {record.id for record in ranked[:retention_limit]}
    for record in ranked[retention_limit:]:
        phase = _proposal_lifecycle_phase(record)
        if phase in protected_phases:
            kept_ids.add(record.id)
            continue
        record.status = ProposalStatus.ARCHIVED
        record.archived_at = current_time
        record.updated_at = current_time
        archived['overflow_candidates'] += 1

    if any(archived.values()):
        _record_system_audit(
            db,
            event_type='candidate_pool_pruned',
            entity_type='strategy_pool',
            entity_id=f'{active_market_scope}:{active_symbol}',
            payload={
                'market_scope': active_market_scope,
                'symbol': active_symbol,
                'retention_limit': retention_limit,
                'candidate_max_age_days': max_age_days,
                **archived,
            },
            created_at=current_time,
        )
    db.flush()
    return archived


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
            current_stage='sync_event_stream',
        )
        db.commit()
        try:
            _set_pipeline_runtime_stage(
                db,
                stage='select_universe',
                current_time=now_tz(),
                status_message='Selecting HK research universe.',
                trigger=trigger,
            )
            universe_selection = get_universe_selection(db, refresh=True, current_time=now_tz())
            purge_out_of_scope_event_history(db, market_scope=str(universe_selection.get("market_scope", "HK")))
            _set_pipeline_runtime_stage(
                db,
                stage='sync_event_stream',
                current_time=now_tz(),
                status_message='Syncing macro event stream.',
                trigger=trigger,
            )
            sync_event_stream(db)
            _set_pipeline_runtime_stage(
                db,
                stage='sync_daily_event_digests',
                current_time=now_tz(),
                status_message='Building macro event digests.',
                trigger=trigger,
            )
            sync_daily_event_digests(db)
            current_time = now_tz()
            _set_pipeline_runtime_stage(
                db,
                stage='build_market_snapshot',
                current_time=current_time,
                status_message='Building market snapshot.',
                trigger=trigger,
            )
            base_snapshot = build_market_snapshot(db)
            _set_pipeline_runtime_stage(
                db,
                stage='market_analyst',
                current_time=now_tz(),
                status_message='Running market analyst.',
                trigger=trigger,
            )
            analyst_state = run_market_analyst(db, base_snapshot, current_time)
            snapshot = _merge_market_snapshot(base_snapshot, analyst_state)
            digest: DailyEventDigest = snapshot["event_digest"]  # type: ignore[assignment]
            symbol = str(snapshot["symbol"])
            market_scope = str(digest.market_scope)
            archive_out_of_scope_strategy_proposals(
                db,
                active_symbol=symbol,
                active_market_scope=market_scope,
                archived_at=current_time,
            )
            previous_active = get_active_strategy(db)
            existing_open_count = db.execute(
                select(func.count())
                .select_from(StrategyProposal)
                .where(StrategyProposal.status != ProposalStatus.ARCHIVED)
            ).scalar_one()

            if force_refresh:
                if previous_active is not None:
                    archive_non_active_strategy_proposals(db, archived_at=current_time)
                else:
                    archive_strategy_proposals(db, archived_at=current_time)
            elif existing_open_count > 0 and previous_active is None:
                archive_strategy_proposals(db, archived_at=current_time)
            elif existing_open_count > 0 and previous_active is not None:
                _set_pipeline_runtime_stage(
                    db,
                    stage='active_health_check',
                    current_time=now_tz(),
                    status_message='Checking active strategy health.',
                    trigger=trigger,
                )
                evaluate_active_strategy_health(db, snapshot, current_time)
                previous_active = get_active_strategy(db)

            _set_pipeline_runtime_stage(
                db,
                stage='strategy_agent',
                current_time=now_tz(),
                status_message='Generating strategy candidates.',
                trigger=trigger,
            )
            blueprints, _ = run_strategy_agent(db=db, symbol=symbol, snapshot=snapshot, current_time=current_time)
            _set_pipeline_runtime_stage(
                db,
                stage='materialize_decisions',
                current_time=now_tz(),
                status_message='Scoring candidates and materializing decisions.',
                trigger=trigger,
            )
            materialize_proposals_and_decisions(
                db,
                snapshot=snapshot,
                digest=digest,
                blueprints=blueprints,
                previous_active=previous_active,
                current_time=current_time,
            )
            prune_strategy_proposals(
                db,
                active_symbol=symbol,
                active_market_scope=market_scope,
                current_time=current_time,
            )
            if previous_active is not None:
                promoted_existing = _promote_existing_real_candidate_over_mock_active(
                    db,
                    active=previous_active,
                    current_time=current_time,
                )
                if promoted_existing is not None:
                    previous_active = promoted_existing
            _set_pipeline_runtime_stage(
                db,
                stage='paper_execution',
                current_time=now_tz(),
                status_message='Executing active paper strategy.',
                trigger=trigger,
            )
            current_active = get_active_strategy(db)
            if current_active is not None:
                execute_active_paper_cycle(
                    db,
                    proposal=current_active,
                    current_time=now_tz(),
                    reason='scheduled_execution',
                )
            _set_pipeline_runtime_stage(
                db,
                stage='active_health_check',
                current_time=now_tz(),
                status_message='Finalizing active strategy health.',
                trigger=trigger,
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
            completed_runtime_status = get_pipeline_runtime_status(db)
            _record_system_audit(
                db,
                event_type='pipeline_sync_completed',
                entity_type='pipeline_runtime',
                entity_id='agent_sync',
                payload={
                    'trigger': trigger,
                    'state': completed_runtime_status.get('current_state'),
                    'current_stage': completed_runtime_status.get('current_stage'),
                    'status_message': completed_runtime_status.get('status_message'),
                    'last_duration_ms': completed_runtime_status.get('last_duration_ms'),
                    'stage_durations_ms': dict(completed_runtime_status.get('stage_durations_ms', {}) or {}),
                    'degraded': bool(completed_runtime_status.get('degraded', False)),
                },
                created_at=current_time,
            )
            readiness = build_live_readiness(db)
            _record_system_audit(
                db,
                event_type='live_readiness_evaluated',
                entity_type='live_readiness',
                entity_id=str(dict(readiness.get('evidence', {})).get('strategy_title') or 'current'),
                payload={
                    'trigger': trigger,
                    **readiness,
                },
                created_at=current_time,
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
            failed_runtime_status = get_pipeline_runtime_status(db)
            _record_system_audit(
                db,
                event_type='pipeline_sync_failed',
                entity_type='pipeline_runtime',
                entity_id='agent_sync',
                payload={
                    'trigger': trigger,
                    'error': str(exc),
                    'consecutive_failures': failure_count,
                    'state': failed_runtime_status.get('current_state'),
                    'current_stage': failed_runtime_status.get('current_stage'),
                    'status_message': failed_runtime_status.get('status_message'),
                    'last_duration_ms': failed_runtime_status.get('last_duration_ms'),
                    'stage_durations_ms': dict(failed_runtime_status.get('stage_durations_ms', {}) or {}),
                    'degraded': bool(failed_runtime_status.get('degraded', False)),
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


def list_event_digests(
    db: Session,
    limit: int = 30,
    *,
    market_scope: str | None = None,
    symbol_scope: str | None = None,
) -> list[DailyEventDigest]:
    query = select(DailyEventDigest)
    if market_scope is not None:
        query = query.where(DailyEventDigest.market_scope == market_scope)
    if symbol_scope is not None:
        query = query.where(DailyEventDigest.symbol_scope == symbol_scope)
    return list(
        db.execute(
            query.order_by(DailyEventDigest.trade_date.desc(), DailyEventDigest.id.desc()).limit(limit)
        ).scalars()
    )
