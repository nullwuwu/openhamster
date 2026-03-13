from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Protocol
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .llm import MiniMaxClient
from .api.models import RuntimeSetting

logger = logging.getLogger("goby_shrimp.llm_gateway")

_RUNTIME_PROVIDER_KEY = "llm.provider"
_RUNTIME_STATUS_KEY = "llm.status"


class LLMProvider:
    MINIMAX = "minimax"
    MOCK = "mock"

    ALL = (MINIMAX, MOCK)


class LLMStatusCode:
    READY = "ready"
    MOCK = "mock"
    MISSING_KEY = "missing_key"
    AUTH_ERROR = "auth_error"
    RATE_LIMITED = "rate_limited"
    NETWORK_ERROR = "network_error"
    PROVIDER_ERROR = "provider_error"
    PARSE_ERROR = "parse_error"


class LLMAdapter(Protocol):
    provider: str
    model: str

    def invoke_json(self, *, system: str, user: str, temperature: float | None = None) -> dict[str, Any]: ...

    def close(self) -> None: ...


@dataclass
class LLMStatus:
    provider: str
    model: str
    status: str
    message: str
    using_mock_fallback: bool
    configured_providers: list[str] = field(default_factory=lambda: list(LLMProvider.ALL))


@dataclass
class LLMInvocationResult:
    payload: dict[str, Any]
    source_kind: str
    status: LLMStatus
    audit_event_type: str | None = None
    audit_payload: dict[str, Any] = field(default_factory=dict)


class MiniMaxAdapter:
    provider = LLMProvider.MINIMAX

    def __init__(self) -> None:
        settings = get_settings()
        self.model = settings.llm.model or "MiniMax-M2.5"
        self.temperature = settings.llm.temperature
        self.client = MiniMaxClient()

    def invoke_json(self, *, system: str, user: str, temperature: float | None = None) -> dict[str, Any]:
        return self.client.chat_json(system=system, user=user, temperature=self.temperature if temperature is None else temperature)

    def close(self) -> None:
        self.client.close()


class MockAdapter:
    provider = LLMProvider.MOCK

    def __init__(self) -> None:
        self.model = "mock"

    def invoke_json(self, *, system: str, user: str, temperature: float | None = None) -> dict[str, Any]:
        return {}

    def close(self) -> None:
        return None


class LLMGateway:
    def _now(self) -> datetime:
        settings = get_settings()
        return datetime.now(ZoneInfo(settings.timezone))

    def _get_runtime_setting(self, db: Session, key: str) -> RuntimeSetting | None:
        return db.execute(select(RuntimeSetting).where(RuntimeSetting.key == key)).scalar_one_or_none()

    def _set_runtime_setting(self, db: Session, key: str, value_json: dict[str, Any]) -> None:
        record = self._get_runtime_setting(db, key)
        if record is None:
            record = RuntimeSetting(key=key, value_json=value_json, updated_at=self._now())
            db.add(record)
        else:
            record.value_json = value_json
            record.updated_at = self._now()

    def get_provider(self, db: Session | None = None) -> str:
        settings = get_settings()
        provider = settings.llm.provider.lower()
        if db is None:
            return provider if provider in LLMProvider.ALL else LLMProvider.MOCK

        record = self._get_runtime_setting(db, _RUNTIME_PROVIDER_KEY)
        if record is not None:
            candidate = str(record.value_json.get("provider", provider)).lower()
            if candidate in LLMProvider.ALL:
                return candidate
        return provider if provider in LLMProvider.ALL else LLMProvider.MOCK

    def _base_status(self, provider: str) -> LLMStatus:
        settings = get_settings()
        model = settings.llm.model if provider == LLMProvider.MINIMAX else "mock"
        if provider == LLMProvider.MOCK:
            return LLMStatus(
                provider=LLMProvider.MOCK,
                model=model,
                status=LLMStatusCode.MOCK,
                message="Mock provider is selected intentionally.",
                using_mock_fallback=False,
            )

        if not settings.integrations.minimax_api_key:
            return LLMStatus(
                provider=LLMProvider.MINIMAX,
                model=model,
                status=LLMStatusCode.MISSING_KEY,
                message="MINIMAX_API_KEY is not configured.",
                using_mock_fallback=True,
            )

        return LLMStatus(
            provider=LLMProvider.MINIMAX,
            model=model,
            status=LLMStatusCode.READY,
            message="MiniMax provider is ready.",
            using_mock_fallback=False,
        )

    def _persist_status(self, db: Session | None, status: LLMStatus) -> None:
        if db is None:
            return
        self._set_runtime_setting(db, _RUNTIME_STATUS_KEY, asdict(status))
        db.flush()

    def get_status(self, db: Session | None = None) -> LLMStatus:
        provider = self.get_provider(db)
        base = self._base_status(provider)
        if db is None:
            return base

        record = self._get_runtime_setting(db, _RUNTIME_STATUS_KEY)
        if record is None:
            return base

        value = record.value_json
        if str(value.get("provider", provider)).lower() != provider:
            return base

        return LLMStatus(
            provider=provider,
            model=str(value.get("model", base.model)),
            status=str(value.get("status", base.status)),
            message=str(value.get("message", base.message)),
            using_mock_fallback=bool(value.get("using_mock_fallback", base.using_mock_fallback)),
            configured_providers=[str(item) for item in value.get("configured_providers", list(LLMProvider.ALL))],
        )

    def set_provider(self, db: Session, provider: str) -> LLMStatus:
        normalized = provider.lower()
        if normalized not in LLMProvider.ALL:
            raise ValueError(f"Unsupported LLM provider: {provider}")

        status = self._base_status(normalized)
        if normalized == LLMProvider.MINIMAX and status.status == LLMStatusCode.MISSING_KEY:
            return status

        self._set_runtime_setting(db, _RUNTIME_PROVIDER_KEY, {"provider": normalized})
        self._persist_status(db, status)
        db.commit()
        db.refresh(self._get_runtime_setting(db, _RUNTIME_PROVIDER_KEY))
        return status

    def _make_adapter(self, provider: str) -> LLMAdapter:
        if provider == LLMProvider.MINIMAX:
            return MiniMaxAdapter()
        return MockAdapter()

    def invoke_json(
        self,
        *,
        db: Session | None,
        task: str,
        system: str,
        user: str,
        schema_hint: dict[str, Any] | None = None,
        temperature: float | None = None,
    ) -> LLMInvocationResult:
        provider = self.get_provider(db)
        base_status = self._base_status(provider)
        if provider == LLMProvider.MOCK:
            self._persist_status(db, base_status)
            return LLMInvocationResult(payload=schema_hint or {}, source_kind=LLMProvider.MOCK, status=base_status)

        if base_status.status != LLMStatusCode.READY:
            fallback_status = LLMStatus(
                provider=provider,
                model=base_status.model,
                status=base_status.status,
                message=base_status.message,
                using_mock_fallback=True,
            )
            self._persist_status(db, fallback_status)
            return LLMInvocationResult(
                payload=schema_hint or {},
                source_kind=LLMProvider.MOCK,
                status=fallback_status,
                audit_event_type="llm_fallback_triggered",
                audit_payload={"task": task, "reason": fallback_status.status, "message": fallback_status.message},
            )

        adapter = self._make_adapter(provider)
        try:
            payload = adapter.invoke_json(system=system, user=user, temperature=temperature)
            success_status = LLMStatus(
                provider=provider,
                model=adapter.model,
                status=LLMStatusCode.READY,
                message=f"{provider} responded successfully.",
                using_mock_fallback=False,
            )
            self._persist_status(db, success_status)
            return LLMInvocationResult(payload=payload, source_kind=provider, status=success_status)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in {401, 403}:
                code = LLMStatusCode.AUTH_ERROR
            elif exc.response.status_code == 429:
                code = LLMStatusCode.RATE_LIMITED
            else:
                code = LLMStatusCode.PROVIDER_ERROR
            message = f"{provider} request failed with HTTP {exc.response.status_code}."
        except httpx.TransportError as exc:
            code = LLMStatusCode.NETWORK_ERROR
            message = f"{provider} network error: {exc}"
        except json.JSONDecodeError as exc:
            code = LLMStatusCode.PARSE_ERROR
            message = f"{provider} returned non-JSON output: {exc}"
        except Exception as exc:
            code = LLMStatusCode.PROVIDER_ERROR
            message = f"{provider} provider error: {exc}"
        finally:
            adapter.close()

        fallback_status = LLMStatus(
            provider=provider,
            model=get_settings().llm.model,
            status=code,
            message=message,
            using_mock_fallback=True,
        )
        self._persist_status(db, fallback_status)
        return LLMInvocationResult(
            payload=schema_hint or {},
            source_kind=LLMProvider.MOCK,
            status=fallback_status,
            audit_event_type="llm_fallback_triggered",
            audit_payload={"task": task, "reason": code, "message": message},
        )


def get_llm_gateway() -> LLMGateway:
    return LLMGateway()
