from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import httpx

from ..config import get_settings


@dataclass
class EventSeed:
    event_id: str
    event_type: str
    market_scope: str
    symbol_scope: str
    published_at: datetime
    source: str
    title: str
    body_ref: str
    tags: list[str] = field(default_factory=list)
    importance: float = 0.5
    sentiment_hint: float = 0.0
    metadata_payload: dict[str, object] = field(default_factory=dict)


class EventProvider(ABC):
    name: str = 'base'
    event_type: str = 'macro'

    @abstractmethod
    def fetch(self, now: datetime, symbol_scope: str = '000300.SH', market_scope: str = 'CN') -> list[EventSeed]:
        pass


class MacroProvider(EventProvider):
    event_type = 'macro'


class DemoMacroProvider(MacroProvider):
    name = 'demo_macro'

    def fetch(self, now: datetime, symbol_scope: str = '000300.SH', market_scope: str = 'CN') -> list[EventSeed]:
        return [
            EventSeed(
                event_id=f'macro-{market_scope}-0',
                event_type=self.event_type,
                market_scope=market_scope,
                symbol_scope='*',
                published_at=now - timedelta(hours=10),
                source=self.name,
                title='政策面维持宽松基调',
                body_ref='政策预期稳定，风险偏好边际修复，但增量刺激有限。',
                tags=['policy', 'macro'],
                importance=0.83,
                sentiment_hint=0.24,
            ),
            EventSeed(
                event_id=f'macro-{market_scope}-1',
                event_type=self.event_type,
                market_scope=market_scope,
                symbol_scope='*',
                published_at=now - timedelta(hours=20),
                source=self.name,
                title='波动率回落但趋势斜率放缓',
                body_ref='当前更适合低频、明确止损、控制换手的策略。',
                tags=['volatility', 'regime'],
                importance=0.68,
                sentiment_hint=0.05,
            ),
        ]


class FREDMacroProvider(MacroProvider):
    name = 'fred'
    BASE_URL = 'https://api.stlouisfed.org/fred/series/observations'
    SERIES = [
        ('FEDFUNDS', 'Federal funds rate', 'lower_is_risk_positive', 0.82),
        ('CPIAUCSL', 'Consumer price index', 'lower_is_risk_positive', 0.75),
        ('UNRATE', 'Unemployment rate', 'lower_is_risk_positive', 0.78),
        ('NFCI', 'Financial conditions index', 'lower_is_risk_positive', 0.70),
    ]

    def __init__(self, api_key: str | None = None):
        settings = get_settings()
        self.api_key = api_key or settings.integrations.fred_api_key

    def fetch(self, now: datetime, symbol_scope: str = '000300.SH', market_scope: str = 'CN') -> list[EventSeed]:
        if not self.api_key:
            raise ValueError('FRED_API_KEY is not configured')

        events: list[EventSeed] = []
        with httpx.Client(timeout=20.0) as client:
            for series_id, label, direction, importance in self.SERIES:
                response = client.get(
                    self.BASE_URL,
                    params={
                        'series_id': series_id,
                        'api_key': self.api_key,
                        'file_type': 'json',
                        'sort_order': 'desc',
                        'limit': 2,
                    },
                )
                response.raise_for_status()
                payload = response.json()
                observations = [item for item in payload.get('observations', []) if item.get('value') not in {'.', None, ''}]
                if not observations:
                    continue
                latest = observations[0]
                previous = observations[1] if len(observations) > 1 else None
                latest_value = _coerce_float(latest.get('value'))
                previous_value = _coerce_float(previous.get('value')) if previous else None
                change = 0.0 if previous_value is None else latest_value - previous_value
                sentiment = _macro_sentiment(change, direction, latest_value, previous_value)
                published_at = _parse_dt(str(latest.get('date') or ''), fallback=now)
                title = f'{label}: {latest_value:.2f}'
                body = (
                    f'Latest {label.lower()} observation is {latest_value:.2f}. '
                    + (f'Previous reading was {previous_value:.2f}. ' if previous_value is not None else '')
                    + f'Change interpreted as market bias {sentiment:+.2f}.'
                )
                events.append(
                    EventSeed(
                        event_id=f'fred-{series_id}-{latest.get("date")}',
                        event_type=self.event_type,
                        market_scope=market_scope,
                        symbol_scope='*',
                        published_at=published_at,
                        source=self.name,
                        title=title,
                        body_ref=body,
                        tags=['fred', 'macro', series_id.lower()],
                        importance=importance,
                        sentiment_hint=sentiment,
                        metadata_payload={
                            'series_id': series_id,
                            'latest_value': latest_value,
                            'previous_value': previous_value,
                            'units': payload.get('units_short') or payload.get('units'),
                        },
                    )
                )
        return events


class WorldBankMacroProvider(MacroProvider):
    name = 'worldbank'
    BASE_URL = 'https://api.worldbank.org/v2/country/{country}/indicator/{indicator}'
    SERIES = [
        ('NY.GDP.MKTP.KD.ZG', 'GDP growth', 'higher_is_risk_positive', 0.78),
        ('FP.CPI.TOTL.ZG', 'Inflation rate', 'lower_is_risk_positive', 0.74),
        ('SL.UEM.TOTL.ZS', 'Unemployment rate', 'lower_is_risk_positive', 0.76),
        ('FR.INR.LEND', 'Lending interest rate', 'lower_is_risk_positive', 0.68),
    ]

    COUNTRY_BY_MARKET = {
        'CN': 'CN',
        'US': 'US',
    }

    def fetch(self, now: datetime, symbol_scope: str = '000300.SH', market_scope: str = 'CN') -> list[EventSeed]:
        country = self.COUNTRY_BY_MARKET.get(market_scope.upper(), 'CN')
        events: list[EventSeed] = []
        with httpx.Client(timeout=20.0) as client:
            for indicator, label, direction, importance in self.SERIES:
                response = client.get(
                    self.BASE_URL.format(country=country, indicator=indicator),
                    params={'format': 'json', 'mrv': 2, 'per_page': 2},
                )
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, list) or len(payload) < 2 or not isinstance(payload[1], list):
                    continue
                observations = [item for item in payload[1] if item.get('value') is not None]
                if not observations:
                    continue
                latest = observations[0]
                previous = observations[1] if len(observations) > 1 else None
                latest_value = _coerce_float(latest.get('value'))
                previous_value = _coerce_float(previous.get('value')) if previous else None
                change = 0.0 if previous_value is None else latest_value - previous_value
                sentiment = _macro_sentiment(change, direction, latest_value, previous_value)
                published_at = _parse_dt(f"{latest.get('date')}-01-01", fallback=now)
                title = f'{label}: {latest_value:.2f}'
                body = (
                    f'Latest {country} {label.lower()} observation is {latest_value:.2f}. '
                    + (f'Previous reading was {previous_value:.2f}. ' if previous_value is not None else '')
                    + f'Change interpreted as market bias {sentiment:+.2f}.'
                )
                events.append(
                    EventSeed(
                        event_id=f'worldbank-{country}-{indicator}-{latest.get("date")}',
                        event_type=self.event_type,
                        market_scope=market_scope,
                        symbol_scope='*',
                        published_at=published_at,
                        source=self.name,
                        title=title,
                        body_ref=body,
                        tags=['worldbank', 'macro', indicator.lower()],
                        importance=importance,
                        sentiment_hint=sentiment,
                        metadata_payload={
                            'indicator': indicator,
                            'country': country,
                            'latest_value': latest_value,
                            'previous_value': previous_value,
                            'source_note': payload[0] if payload and isinstance(payload[0], dict) else {},
                        },
                    )
                )
        return events


class ChainedMacroProvider(MacroProvider):
    name = 'macro_chain'

    def __init__(self, providers: list[MacroProvider]):
        self.providers = providers
        self.provider_chain = [provider.name for provider in providers]
        self.provider_name = self.name
        self.provider_message = ''

    def fetch(self, now: datetime, symbol_scope: str = '000300.SH', market_scope: str = 'CN') -> list[EventSeed]:
        errors: list[str] = []
        preferred = self.providers[0].name if self.providers else self.name
        for index, provider in enumerate(self.providers):
            try:
                events = provider.fetch(now=now, symbol_scope=symbol_scope, market_scope=market_scope)
                if not events:
                    errors.append(f'{provider.name}: empty result')
                    continue
                self.provider_name = provider.name
                if index == 0:
                    self.provider_message = f'{provider.name} macro pipeline is healthy.'
                else:
                    self.provider_message = (
                        f'{provider.name} macro pipeline is serving as fallback after {preferred} became unavailable.'
                    )
                return events
            except Exception as exc:
                errors.append(f'{provider.name}: {exc}')

        self.provider_name = self.name
        self.provider_message = '; '.join(errors)
        raise RuntimeError(self.provider_message or 'all macro providers failed')


def _parse_dt(value: str, fallback: datetime) -> datetime:
    if not value.strip():
        return fallback
    normalized = value.strip().replace('Z', '+00:00')
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        try:
            return datetime.strptime(value.strip(), '%Y-%m-%d')
        except ValueError:
            return fallback


def _coerce_float(value: object) -> float:
    return float(str(value))


def _macro_sentiment(change: float, direction: str, latest: float, previous: float | None) -> float:
    if previous is None:
        return 0.0
    magnitude = min(abs(change) / max(abs(previous), 1e-6), 1.0)
    sign = -1.0 if direction == 'lower_is_risk_positive' else 1.0
    return round(max(-0.35, min(0.35, sign * -change * magnitude)), 3)


def get_event_providers() -> list[EventProvider]:
    settings = get_settings()
    if settings.events.macro_provider.lower() == 'fred':
        return [ChainedMacroProvider([FREDMacroProvider(), WorldBankMacroProvider()])]
    return [DemoMacroProvider()]
