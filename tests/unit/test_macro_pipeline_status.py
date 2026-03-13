from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

from goby_shrimp.api.db import SessionLocal, init_database
from goby_shrimp.api.models import AuditRecord, EventRecord, EventType
from goby_shrimp.api.services import get_macro_pipeline_status, get_pipeline_runtime_status, sync_event_stream
from goby_shrimp.api.services import now_tz


class _BrokenMacroProvider:
    provider_name = 'fred'

    def fetch(self, now: datetime, symbol_scope: str = '*', market_scope: str = 'CN'):
        raise RuntimeError('upstream unavailable')


def test_sync_event_stream_marks_macro_provider_degraded(monkeypatch) -> None:
    init_database()
    monkeypatch.setattr('goby_shrimp.api.services.get_event_providers', lambda: [_BrokenMacroProvider()])

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
    monkeypatch.setattr('goby_shrimp.api.services.get_event_providers', lambda: [_BrokenMacroProvider()])

    with SessionLocal() as db:
        current_time = now_tz()
        db.add(
            EventRecord(
                event_id='fred-FEDFUNDS-2026-03-10',
                event_type=EventType.MACRO,
                market_scope='CN',
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
    with SessionLocal() as db:
        status = get_pipeline_runtime_status(db)
        assert status['current_state'] == 'idle'
        assert status['consecutive_failures'] == 0
        assert status['stalled'] is False
