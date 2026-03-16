from __future__ import annotations

import importlib
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from goby_shrimp.api.app import app
from goby_shrimp.config import get_settings
from goby_shrimp.runtime_state import delete_runtime_state_keys, get_runtime_state_json, set_runtime_state_json


@pytest.fixture(autouse=True)
def reset_runtime_state(monkeypatch) -> None:
    settings = get_settings()
    now = datetime.now(ZoneInfo(settings.timezone))
    app_module = importlib.import_module("goby_shrimp.api.app")
    services_module = importlib.import_module("goby_shrimp.api.services")

    monkeypatch.setattr(app_module, "sync_strategy_snapshots", lambda db: None)
    monkeypatch.setattr(app_module, "sync_agent_state", lambda db, **kwargs: None)
    monkeypatch.setattr(services_module, "sync_agent_state", lambda db, **kwargs: None)

    runtime_keys = ["llm.provider", "llm.status", "pipeline.runtime.status"]
    previous_records = {
        key: get_runtime_state_json(key)
        for key in runtime_keys
        if get_runtime_state_json(key) is not None
    }
    delete_runtime_state_keys(runtime_keys)
    set_runtime_state_json("llm.provider", {"provider": "mock"}, updated_at=now)
    try:
        yield
    finally:
        delete_runtime_state_keys(runtime_keys)
        for key, value in previous_records.items():
            set_runtime_state_json(key, value, updated_at=now)


def test_healthz() -> None:
    with TestClient(app) as client:
        response = client.get('/healthz')
        assert response.status_code == 200
        assert response.json()['status'] == 'ok'


def test_strategy_list() -> None:
    with TestClient(app) as client:
        response = client.get('/api/v1/strategies')
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert data
        assert 'supported_markets' in data[0]
        assert 'market_bias' in data[0]
        assert 'knowledge_families' in data[0]
        assert 'strategy_family_label_zh' in data[0]


def test_command_center_includes_llm_status() -> None:
    with TestClient(app) as client:
        response = client.get('/api/v1/command')
        assert response.status_code == 200
        data = response.json()
        assert 'llm_status' in data
        assert 'runtime_status' in data
        assert 'live_readiness' in data
        assert data['live_readiness']['status'] in {'ready_candidate', 'paper_building_evidence', 'not_ready'}
        assert isinstance(data['live_readiness']['score'], int)
        assert isinstance(data['live_readiness']['blockers'], list)
        assert isinstance(data['live_readiness']['next_actions'], list)
        assert isinstance(data['live_readiness']['dimensions'], dict)
        assert isinstance(data['live_readiness_history'], list)
        assert 'live_readiness_change' in data
        assert data['runtime_status']['current_state'] in {'idle', 'running', 'degraded', 'stalled', 'failed'}
        assert 'consecutive_failures' in data['runtime_status']
        assert 'current_stage' in data['runtime_status']
        assert 'stage_durations_ms' in data['runtime_status']
        assert 'process_started_at' in data['runtime_status']
        assert 'process_uptime_seconds' in data['runtime_status']
        assert 'startup_mode' in data['runtime_status']
        assert 'local_logs_available' in data['runtime_status']
        assert 'runtime_sync_history' in data
        assert isinstance(data['runtime_sync_history'], list)
        assert 'provider_migration' in data
        assert 'provider_migration_history' in data
        assert data['provider_migration']['current_provider'] in {'minimax', 'mock'}
        assert 'summary' in data['provider_migration']
        assert 'current' in data['provider_migration']
        assert isinstance(data['provider_migration_history'], list)
        assert data['llm_status']['provider'] in {'minimax', 'mock'}
        assert 'event_lane_sources' in data['market_snapshot']
        assert set(data['market_snapshot']['event_lane_sources']) == {'macro'}
        assert data['market_snapshot']['market_profile']['market_scope'] == 'HK'
        assert data['market_snapshot']['market_profile']['benchmark_symbol'] == '2800.HK'
        assert data['market_snapshot']['universe_selection']['market_scope'] == 'HK'
        assert data['market_snapshot']['universe_selection']['selected_symbol'].endswith('.HK')
        assert 'selection_reason' in data['market_snapshot']['universe_selection']
        assert 'top_factors' in data['market_snapshot']['universe_selection']
        assert 'macro_status' in data['market_snapshot']
        assert data['market_snapshot']['macro_status']['provider']
        assert 'reliability_score' in data['market_snapshot']['macro_status']
        assert 'provider_chain' in data['market_snapshot']['macro_status']
        assert 'freshness_tier' in data['market_snapshot']['macro_status']
        assert data['latest_event_digest']['market_scope'] == data['market_snapshot']['event_digest']['market_scope']
        assert data['latest_event_digest']['symbol_scope'] == data['market_snapshot']['event_digest']['symbol_scope']
        assert 'operational_acceptance' in data['active_strategy']
        if data['active_strategy']['proposal'] is not None:
            assert 'latest_execution' in data['active_strategy']['paper_trading']
            latest_execution = data['active_strategy']['paper_trading']['latest_execution']
            if latest_execution is not None:
                assert 'latest_price_as_of' in latest_execution
                assert 'price_age_hours' in latest_execution
                assert 'price_changed' in latest_execution
                assert 'equity_changed' in latest_execution
                assert 'rebalance_triggered' in latest_execution
                assert 'explanation' in latest_execution


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
        assert any('backtest_gate' in item['evidence_pack'].get('quality_report', {}) for item in data)
        assert any('knowledge_families_used' in item['evidence_pack'].get('quality_report', {}) for item in data)
        ranked = next(item for item in data if 'pool_ranking' in item['evidence_pack'].get('quality_report', {}))
        ranking = ranked['evidence_pack']['quality_report']['pool_ranking']
        assert 'percentile' in ranking
        assert 'median_gap' in ranking
        backtest_gate = ranked['evidence_pack']['quality_report']['backtest_gate']
        assert 'eligible_for_paper' in backtest_gate
        assert 'summary' in backtest_gate
        track_record = ranked['evidence_pack']['quality_report']['track_record']
        assert 'trend' in track_record
        assert 'stable_streak' in track_record
        assert 'baseline_delta_summary' in ranked['evidence_pack']['quality_report']
        assert 'novelty_assessment' in ranked['evidence_pack']['quality_report']['verdict']


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


def test_runtime_llm_switch_records_provider_migration_events() -> None:
    with TestClient(app) as client:
        response = client.patch('/api/v1/runtime/llm', json={'provider': 'mock'})
        assert response.status_code == 200
        audits = client.get('/api/v1/audit/events').json()
        event_types = {item['event_type'] for item in audits}
        assert 'llm_provider_switched' in event_types
        assert 'provider_cohort_started' in event_types
        assert 'provider_comparison_window_closed' in event_types


def test_strategy_payloads_include_knowledge_fields() -> None:
    with TestClient(app) as client:
        proposals = client.get('/api/v1/research/proposals').json()
        assert proposals
        quality_report = proposals[0]['evidence_pack']['quality_report']
        assert 'knowledge_families_used' in quality_report
        assert 'baseline_delta_summary' in quality_report
        assert 'novelty_assessment' in quality_report['verdict']


def test_runtime_llm_switch_queues_background_sync(monkeypatch) -> None:
    app_module = importlib.import_module("goby_shrimp.api.app")
    calls: list[str] = []

    monkeypatch.setattr(app_module, "_run_runtime_provider_switch_sync_job", lambda: calls.append("runtime_provider_switch"))

    with TestClient(app) as client:
        response = client.patch('/api/v1/runtime/llm', json={'provider': 'mock'})
        assert response.status_code == 200

    assert calls == ["runtime_provider_switch"]


def test_runtime_sync_can_be_triggered(monkeypatch) -> None:
    app_module = importlib.import_module("goby_shrimp.api.app")
    calls: list[str] = []

    monkeypatch.setattr(app_module, "_run_manual_sync_job", lambda: calls.append("manual_api"))

    with TestClient(app) as client:
        response = client.post('/api/v1/runtime/sync')
        assert response.status_code == 200
        assert response.json()['current_state'] in {'idle', 'running', 'degraded', 'failed', 'stalled'}

    assert calls == ["manual_api"]


def test_runtime_sync_can_be_triggered_when_previous_run_is_stalled(monkeypatch) -> None:
    app_module = importlib.import_module("goby_shrimp.api.app")
    calls: list[str] = []
    now = datetime.now(ZoneInfo(get_settings().timezone))

    monkeypatch.setattr(app_module, "_run_manual_sync_job", lambda: calls.append("manual_api"))

    set_runtime_state_json(
        "pipeline.runtime.status",
        {
            "current_state": "running",
            "status_message": "stuck",
            "last_run_at": (now.replace(microsecond=0) - timedelta(minutes=20)).isoformat(),
            "last_success_at": None,
            "last_failure_at": None,
            "consecutive_failures": 0,
            "expected_next_run_at": None,
            "last_duration_ms": 0,
            "last_trigger": "scheduler",
            "degraded": False,
        },
        updated_at=now,
    )

    with TestClient(app) as client:
        response = client.post('/api/v1/runtime/sync')
        assert response.status_code == 200
        assert response.json()['current_state'] == 'stalled'

    assert calls == ["manual_api"]


def test_runtime_logs_endpoint_returns_tail(monkeypatch, tmp_path) -> None:
    app_module = importlib.import_module("goby_shrimp.api.app")
    out_log = tmp_path / "gobyshrimp-api.out.log"
    out_log.write_text("line-1\nline-2\nline-3\n", encoding="utf-8")
    monkeypatch.setattr(app_module, "RUNTIME_LOG_PATHS", {"out": out_log, "err": tmp_path / "missing.err.log"})

    with TestClient(app) as client:
        response = client.get('/api/v1/runtime/logs?stream=out&lines=20')
        assert response.status_code == 200
        data = response.json()
        assert data['stream'] == 'out'
        assert data['exists'] is True
        assert data['path'] == str(out_log)
        assert data['lines'] == ['line-1', 'line-2', 'line-3']

        missing = client.get('/api/v1/runtime/logs?stream=err&lines=20')
        assert missing.status_code == 200
        missing_data = missing.json()
        assert missing_data['stream'] == 'err'
        assert missing_data['exists'] is False
        assert missing_data['lines'] == []


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
                'symbol': '2800.HK',
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
