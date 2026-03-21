from __future__ import annotations

from datetime import datetime

import pytest

from openhamster.config import get_settings
from openhamster.events.providers import ChainedMacroProvider, FREDMacroProvider, WorldBankMacroProvider


class _FakeResponse:
    def __init__(self, *, json_payload=None, text: str = "") -> None:
        self._json_payload = json_payload or {}
        self.text = text

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self._json_payload


class _FakeClient:
    def __init__(self, *args, **kwargs) -> None:
        return None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def get(self, url: str, params=None):
        if "fred/series/observations" in url:
            series_id = params["series_id"]
            return _FakeResponse(
                json_payload={
                    "observations": [
                        {"date": "2026-03-10", "value": "3.2"},
                        {"date": "2026-02-10", "value": "3.0"},
                    ],
                    "units_short": "pct",
                    "series_id": series_id,
                }
            )
        if "api.worldbank.org" in url:
            indicator = url.rstrip("/").split("/")[-1]
            return _FakeResponse(
                json_payload=[
                    {"sourceid": "2", "lastupdated": "2026-03-01"},
                    [
                        {"date": "2025", "value": 4.2},
                        {"date": "2024", "value": 3.8},
                    ],
                ]
            )
        raise AssertionError(f"Unexpected GET url: {url}")


def test_fred_macro_provider_requires_key(monkeypatch) -> None:
    settings = get_settings()
    patched = settings.model_copy(
        deep=True,
        update={"integrations": settings.integrations.model_copy(update={"fred_api_key": ""})},
    )
    monkeypatch.setattr("openhamster.events.providers.get_settings", lambda: patched)
    provider = FREDMacroProvider(api_key="")
    with pytest.raises(ValueError, match="FRED_API_KEY"):
        provider.fetch(datetime(2026, 3, 11))


def test_fred_macro_provider_normalizes_events(monkeypatch) -> None:
    monkeypatch.setattr("openhamster.events.providers.httpx.Client", _FakeClient)
    provider = FREDMacroProvider(api_key="fred-test")

    events = provider.fetch(datetime(2026, 3, 11))

    assert len(events) == 4
    assert all(event.event_type == "macro" for event in events)
    assert all(event.source == "fred" for event in events)
    assert any("fedfunds" in event.tags for event in events)


def test_worldbank_macro_provider_normalizes_events(monkeypatch) -> None:
    monkeypatch.setattr("openhamster.events.providers.httpx.Client", _FakeClient)
    provider = WorldBankMacroProvider()

    events = provider.fetch(datetime(2026, 3, 11))

    assert len(events) == 4
    assert all(event.event_type == "macro" for event in events)
    assert all(event.source == "worldbank" for event in events)
    assert any("worldbank" in event.tags for event in events)


def test_chained_macro_provider_uses_secondary_when_primary_fails(monkeypatch) -> None:
    class _FailingFRED(FREDMacroProvider):
        def fetch(self, now: datetime, symbol_scope: str = '2800.HK', market_scope: str = 'HK'):
            raise RuntimeError("fred down")

    monkeypatch.setattr("openhamster.events.providers.httpx.Client", _FakeClient)
    provider = ChainedMacroProvider([_FailingFRED(api_key="fred-test"), WorldBankMacroProvider()])

    events = provider.fetch(datetime(2026, 3, 11))

    assert events
    assert provider.provider_name == "worldbank"
    assert "fallback" in provider.provider_message.lower()
