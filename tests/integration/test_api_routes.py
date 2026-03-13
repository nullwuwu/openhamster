from __future__ import annotations

import importlib
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from goby_shrimp.api.app import app
from goby_shrimp.api.db import SessionLocal
from goby_shrimp.api.models import RuntimeSetting
from goby_shrimp.config import get_settings


@pytest.fixture(autouse=True)
def reset_runtime_state(monkeypatch) -> None:
    settings = get_settings()
    now = datetime.now(ZoneInfo(settings.timezone))
    app_module = importlib.import_module("goby_shrimp.api.app")
    services_module = importlib.import_module("goby_shrimp.api.services")

    monkeypatch.setattr(app_module, "sync_strategy_snapshots", lambda db: None)
    monkeypatch.setattr(app_module, "sync_agent_state", lambda db, trigger="manual": None)
    monkeypatch.setattr(services_module, "sync_agent_state", lambda db, force_refresh=False, trigger="manual": None)

    with SessionLocal() as db:
        db.execute(
            delete(RuntimeSetting).where(
                RuntimeSetting.key.in_(["llm.provider", "llm.status", "pipeline.runtime.status"])
            )
        )
        db.add(
            RuntimeSetting(
                key="llm.provider",
                value_json={"provider": "mock"},
                updated_at=now,
            )
        )
        db.commit()


def test_healthz() -> None:
    with TestClient(app) as client:
        response = client.get('/healthz')
        assert response.status_code == 200
        assert response.json()['status'] == 'ok'


def test_strategy_list() -> None:
    with TestClient(app) as client:
        response = client.get('/api/v1/strategies')
        assert response.status_code == 200
        assert isinstance(response.json(), list)


def test_command_center_includes_llm_status() -> None:
    with TestClient(app) as client:
        response = client.get('/api/v1/command')
        assert response.status_code == 200
        data = response.json()
        assert 'llm_status' in data
        assert 'runtime_status' in data
        assert data['runtime_status']['current_state'] in {'idle', 'running', 'degraded', 'stalled', 'failed'}
        assert 'consecutive_failures' in data['runtime_status']
        assert data['llm_status']['provider'] in {'minimax', 'mock'}
        assert 'event_lane_sources' in data['market_snapshot']
        assert set(data['market_snapshot']['event_lane_sources']) == {'macro'}
        assert 'macro_status' in data['market_snapshot']
        assert data['market_snapshot']['macro_status']['provider']
        assert 'reliability_score' in data['market_snapshot']['macro_status']
        assert 'provider_chain' in data['market_snapshot']['macro_status']
        assert 'freshness_tier' in data['market_snapshot']['macro_status']
        assert 'operational_acceptance' in data['active_strategy']


def test_risk_decisions_include_governance_report() -> None:
    with TestClient(app) as client:
        response = client.get('/api/v1/risk/decisions')
        assert response.status_code == 200
        data = response.json()
        assert data
        assert any('governance_report' in item['evidence_pack'] for item in data)
        assert any('quality_report' in item['evidence_pack'] for item in data)
        assert any('oos_validation' in item['evidence_pack'].get('quality_report', {}) for item in data)
        assert any('track_record' in item['evidence_pack'].get('quality_report', {}) for item in data)
        lifecycle = next(
            item['evidence_pack']['governance_report']['lifecycle']
            for item in data
            if 'lifecycle' in item['evidence_pack'].get('governance_report', {})
        )
        assert lifecycle['eta_kind'] in {'next_sync_window', 'cooldown_window', 'quality_revalidation', 'review_pending', 'unknown'}
        assert 'estimated_next_eligible_at' in lifecycle


def test_research_proposals_include_pool_ranking() -> None:
    with TestClient(app) as client:
        response = client.get('/api/v1/research/proposals')
        assert response.status_code == 200
        data = response.json()
        assert data
        assert any('pool_ranking' in item['evidence_pack'].get('quality_report', {}) for item in data)
        ranked = next(item for item in data if 'pool_ranking' in item['evidence_pack'].get('quality_report', {}))
        ranking = ranked['evidence_pack']['quality_report']['pool_ranking']
        assert 'percentile' in ranking
        assert 'median_gap' in ranking
        track_record = ranked['evidence_pack']['quality_report']['track_record']
        assert 'trend' in track_record
        assert 'stable_streak' in track_record


def test_acceptance_report_endpoint() -> None:
    with TestClient(app) as client:
        response = client.get('/api/v1/ops/acceptance-report?window_days=30')
        assert response.status_code == 200
        data = response.json()
        assert data['window_days'] == 30
        assert data['status'] in {'healthy', 'watch', 'attention'}
        assert isinstance(data['key_findings'], list)
        assert isinstance(data['next_actions'], list)
        assert 'track_record' in data['quality']
        assert 'status' in data['operations']
        assert 'provider_chain' in data['macro']
        assert 'health_score_30d' in data['macro']
        assert 'phase' in data['governance']


def test_runtime_llm_can_switch_to_mock() -> None:
    with TestClient(app) as client:
        response = client.patch('/api/v1/runtime/llm', json={'provider': 'mock'})
        assert response.status_code == 200
        data = response.json()
        assert data['provider'] == 'mock'
        assert data['status'] == 'mock'


def test_runtime_sync_can_be_triggered(monkeypatch) -> None:
    app_module = importlib.import_module("goby_shrimp.api.app")
    calls: list[str] = []

    monkeypatch.setattr(app_module, "_run_manual_sync_job", lambda: calls.append("manual_api"))

    with TestClient(app) as client:
        response = client.post('/api/v1/runtime/sync')
        assert response.status_code == 200
        assert response.json()['current_state'] in {'idle', 'running', 'degraded', 'failed', 'stalled'}

    assert calls == ["manual_api"]


def test_runtime_llm_rejects_minimax_without_key(monkeypatch) -> None:
    gateway_module = importlib.import_module("goby_shrimp.llm_gateway")
    original_settings = get_settings()
    patched_settings = original_settings.model_copy(
        deep=True,
        update={
            'integrations': original_settings.integrations.model_copy(
                update={'minimax_api_key': ''}
            ),
            'llm': original_settings.llm.model_copy(update={'provider': 'minimax'}),
        },
    )
    monkeypatch.setattr(gateway_module, "get_settings", lambda: patched_settings)

    with TestClient(app) as client:
        response = client.patch('/api/v1/runtime/llm', json={'provider': 'minimax'})
        assert response.status_code == 400
        assert 'MINIMAX_API_KEY' in response.text


def test_create_backtest_run_queued(monkeypatch) -> None:
    def _noop(run_id: str) -> None:
        return None

    app_module = importlib.import_module("goby_shrimp.api.app")
    monkeypatch.setattr(app_module, "execute_backtest_run", _noop)

    with TestClient(app) as client:
        response = client.post(
            '/api/v1/backtests/runs',
            json={
                'symbol': '000300.SH',
                'strategy_name': 'ma_cross',
                'provider_name': 'stooq',
                'start_date': '2020-01-01',
                'end_date': '2021-01-01',
                'initial_capital': 100000,
                'strategy_params': {'short_window': 5, 'long_window': 20},
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert 'run_id' in data
        assert data['status'] == 'queued'
