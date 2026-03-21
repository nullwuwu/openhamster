from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import inspect, select

from openhamster.api.db import SessionLocal, engine, init_database
from openhamster.api.models import AuditRecord, EventRecord, EventType
from openhamster.api.services import (
    _set_pipeline_runtime_stage,
    _set_pipeline_runtime_status,
    get_macro_pipeline_status,
    get_pipeline_runtime_status,
    get_universe_selection,
    now_tz,
    sync_event_stream,
)
from openhamster.runtime_state import delete_runtime_state_keys


class _BrokenMacroProvider:
    provider_name = 'fred'

    def fetch(self, now: datetime, symbol_scope: str = '*', market_scope: str = 'HK'):
        raise RuntimeError('upstream unavailable')


def test_sync_event_stream_marks_macro_provider_degraded(monkeypatch) -> None:
    init_database()
    monkeypatch.setattr('openhamster.api.services.get_event_providers', lambda: [_BrokenMacroProvider()])

    with SessionLocal() as db:
        sync_event_stream(db)
        status = get_macro_pipeline_status(db)
        assert status['status'] == 'degraded'
        assert status['degraded'] is True
        assert status['reliability_tier'] == 'provider_failed'
        assert status['freshness_tier'] in {'fresh', 'aging', 'stale', 'expired'}
        audits = list(
            db.execute(
                select(AuditRecord).where(AuditRecord.event_type == 'macro_provider_degraded')
            ).scalars()
        )
        assert audits


def test_sync_event_stream_reuses_last_known_macro_context(monkeypatch) -> None:
    init_database()
    monkeypatch.setattr('openhamster.api.services.get_event_providers', lambda: [_BrokenMacroProvider()])

    with SessionLocal() as db:
        current_time = now_tz()
        db.add(
            EventRecord(
                event_id='fred-FEDFUNDS-2026-03-10',
                event_type=EventType.MACRO,
                market_scope='HK',
                symbol_scope='*',
                published_at=current_time,
                source='fred',
                title='Federal funds rate: 4.25',
                body_ref='Latest usable macro context.',
                tags=['fred', 'macro'],
                importance=0.8,
                sentiment_hint=0.1,
                metadata_payload={},
                created_at=current_time,
            )
        )
        db.commit()

        sync_event_stream(db)

        status = get_macro_pipeline_status(db)
        assert status['status'] == 'degraded'
        assert status['using_last_known_context'] is True
        assert status['fallback_event_count'] >= 1
        assert status['reliability_tier'] == 'last_known_context'
        assert status['freshness_hours'] is not None
        fallback_records = list(
            db.execute(
                select(EventRecord).where(EventRecord.source == 'fred_last_good')
            ).scalars()
        )
        assert fallback_records
        audits = list(
            db.execute(
                select(AuditRecord).where(AuditRecord.event_type == 'macro_provider_fallback_applied')
            ).scalars()
        )
        assert audits


def test_pipeline_runtime_status_defaults_to_idle() -> None:
    init_database()
    delete_runtime_state_keys(["pipeline.runtime.status"])
    with SessionLocal() as db:
        status = get_pipeline_runtime_status(db)
        assert status['current_state'] == 'idle'
        assert status['consecutive_failures'] == 0
        assert status['stalled'] is False


def test_pipeline_stage_durations_reset_for_new_run() -> None:
    init_database()
    delete_runtime_state_keys(["pipeline.runtime.status"])
    with SessionLocal() as db:
        started_at = now_tz()
        _set_pipeline_runtime_status(
            db,
            current_state='running',
            status_message='run-1',
            current_time=started_at,
            current_stage='sync_event_stream',
            last_trigger='scheduler',
        )
        _set_pipeline_runtime_stage(
            db,
            stage='strategy_agent',
            current_time=started_at + timedelta(seconds=2),
            status_message='run-1-stage',
            trigger='scheduler',
        )
        _set_pipeline_runtime_status(
            db,
            current_state='idle',
            status_message='done',
            current_time=started_at + timedelta(seconds=3),
            last_success_at=(started_at + timedelta(seconds=3)).isoformat(),
            last_trigger='scheduler',
        )
        first_run = get_pipeline_runtime_status(db)
        assert first_run['stage_durations_ms'].get('sync_event_stream') == 2000
        assert first_run['stage_durations_ms'].get('strategy_agent') == 1000

        second_started_at = started_at + timedelta(minutes=10)
        _set_pipeline_runtime_status(
            db,
            current_state='running',
            status_message='run-2',
            current_time=second_started_at,
            current_stage='sync_event_stream',
            last_trigger='scheduler',
        )
        second_run = get_pipeline_runtime_status(db)
        assert second_run['stage_durations_ms'] == {}


def test_dynamic_hk_universe_selection_picks_hk_symbol(monkeypatch) -> None:
    init_database()
    monkeypatch.setattr(
        'openhamster.api.services.fetch_hk_universe_candidates',
        lambda **kwargs: [
            {
                'symbol': '0700.HK',
                'name': 'Tencent',
                'rank': 1,
                'latest_price': 320.0,
                'change_pct': 2.1,
                'amplitude_pct': 3.8,
                'turnover_millions': 1800.0,
                'score': 1852.5,
                'factor_scores': {'liquidity': 50.0, 'momentum': 6.3, 'stability': 12.1, 'price_quality': 10.0},
                'reason_tags': ['very_high_liquidity', 'positive_momentum', 'controlled_range'],
                'selection_reason': 'Very high turnover supports entry and exit capacity.',
                'source': 'akshare',
            },
            {
                'symbol': '2800.HK',
                'name': 'Tracker Fund',
                'rank': 2,
                'latest_price': 25.7,
                'change_pct': 0.4,
                'amplitude_pct': 2.6,
                'turnover_millions': 800.0,
                'score': 810.0,
                'factor_scores': {'liquidity': 38.0, 'momentum': 1.2, 'stability': 13.5, 'price_quality': 10.0},
                'reason_tags': ['high_liquidity', 'controlled_range', 'institutional_price_band'],
                'selection_reason': 'High turnover supports stable execution.',
                'source': 'akshare',
            },
        ],
    )

    with SessionLocal() as db:
        selection = get_universe_selection(db, refresh=True, current_time=now_tz())
        assert selection['market_scope'] == 'HK'
        assert selection['selected_symbol'] == '0700.HK'
        assert len(selection['candidates']) == 2
        assert selection['selection_reason']
        assert selection['top_factors']


def test_macro_pipeline_health_history_aggregates_recent_audits() -> None:
    init_database()
    with SessionLocal() as db:
        baseline = get_macro_pipeline_status(db)
        current_time = now_tz()
        stale_time = current_time - timedelta(days=40)
        db.add_all(
            [
                AuditRecord(
                    run_id='system-governance',
                    decision_id='macro-health-1',
                    event_type='macro_provider_degraded',
                    entity_type='macro_pipeline',
                    entity_id='fred',
                    payload={},
                    created_at=current_time - timedelta(days=1),
                ),
                AuditRecord(
                    run_id='system-governance',
                    decision_id='macro-health-2',
                    event_type='macro_provider_degraded',
                    entity_type='macro_pipeline',
                    entity_id='fred',
                    payload={},
                    created_at=current_time - timedelta(days=2),
                ),
                AuditRecord(
                    run_id='system-governance',
                    decision_id='macro-health-3',
                    event_type='macro_provider_fallback_applied',
                    entity_type='macro_pipeline',
                    entity_id='fred',
                    payload={},
                    created_at=current_time - timedelta(hours=12),
                ),
                AuditRecord(
                    run_id='system-governance',
                    decision_id='macro-health-4',
                    event_type='macro_provider_recovered',
                    entity_type='macro_pipeline',
                    entity_id='fred',
                    payload={},
                    created_at=current_time - timedelta(hours=6),
                ),
                AuditRecord(
                    run_id='system-governance',
                    decision_id='macro-health-stale',
                    event_type='macro_provider_degraded',
                    entity_type='macro_pipeline',
                    entity_id='fred',
                    payload={},
                    created_at=stale_time,
                ),
            ]
        )
        db.commit()

        status = get_macro_pipeline_status(db)

    assert status['degraded_count_30d'] - baseline['degraded_count_30d'] == 2
    assert status['fallback_count_30d'] - baseline['fallback_count_30d'] == 1
    assert status['recovery_count_30d'] - baseline['recovery_count_30d'] == 1
    expected_score = round(
        max(
            0.1,
            min(
                1.0,
                1.0
                - status['degraded_count_30d'] * 0.12
                - status['fallback_count_30d'] * 0.06
                + status['recovery_count_30d'] * 0.02,
            ),
        ),
        2,
    )
    assert status['health_score_30d'] == expected_score


def test_init_database_repairs_runtime_indexes() -> None:
    init_database()
    inspector = inspect(engine)

    audit_indexes = {item['name'] for item in inspector.get_indexes('audit_records')}
    event_indexes = {item['name'] for item in inspector.get_indexes('event_records')}
    digest_indexes = {item['name'] for item in inspector.get_indexes('daily_event_digests')}

    assert 'ix_audit_records_event_created_at' in audit_indexes
    assert 'ix_audit_records_entity_event_created_at' in audit_indexes
    assert 'ix_audit_records_decision_created_at' in audit_indexes
    assert 'ix_event_records_market_published_at' in event_indexes
    assert 'ix_daily_event_digests_scope_trade_date' in digest_indexes
