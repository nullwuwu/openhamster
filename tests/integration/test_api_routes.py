from __future__ import annotations

import importlib

from fastapi.testclient import TestClient

from quant_trader.api.app import app


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


def test_create_backtest_run_queued(monkeypatch) -> None:
    def _noop(run_id: str) -> None:
        return None

    app_module = importlib.import_module("quant_trader.api.app")
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
