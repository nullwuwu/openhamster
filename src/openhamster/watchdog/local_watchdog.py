from __future__ import annotations

import json
import os
import subprocess
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests

from ..config import get_settings
from ..runtime_state import get_runtime_state_json, set_runtime_state_json

WATCHDOG_LATEST_KEY = "runtime.watchdog.latest"
WATCHDOG_HISTORY_KEY = "runtime.watchdog.history"


def _now() -> datetime:
    settings = get_settings()
    return datetime.now(ZoneInfo(settings.timezone))


def _health_url() -> str:
    return os.environ.get("OPENHAMSTER_WATCHDOG_HEALTH_URL", "http://127.0.0.1:8000/healthz")


def _command_url() -> str:
    return os.environ.get("OPENHAMSTER_WATCHDOG_COMMAND_URL", "http://127.0.0.1:8000/api/v1/command")


def _service_label() -> str:
    return os.environ.get("OPENHAMSTER_WATCHDOG_TARGET_LABEL", "com.openhamster.api")


def _error_log_path() -> Path:
    return Path(os.environ.get("OPENHAMSTER_STDERR_LOG_PATH", "logs/openhamster-api.err.log"))


def _tail_log_signals(path: Path, *, limit: int = 80) -> tuple[int, list[str]]:
    if not path.exists():
        return 0, []
    signals: list[str] = []
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in deque(handle, maxlen=limit):
            text = line.rstrip("\n")
            lowered = text.lower()
            if "shell-init: error retrieving current directory" in lowered:
                continue
            if "❌ no_go" in lowered or "❌ no-go" in lowered:
                continue
            if any(token in lowered for token in ("traceback", "error", "exception", "unhandled", "fatal")):
                signals.append(text)
    return len(signals), signals[-8:]


def _json_get(url: str, timeout: float = 5.0) -> dict[str, Any] | None:
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    payload = response.json()
    return payload if isinstance(payload, dict) else None


def _restart_service(reason: str) -> bool:
    label = _service_label()
    target = f"gui/{os.getuid()}/{label}"
    completed = subprocess.run(
        ["launchctl", "kickstart", "-k", target],
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.returncode == 0


def _snapshot_summary(status: str, issues: list[str]) -> str:
    if not issues:
        return "Watchdog found no blocking runtime issue."
    if status == "critical":
        return f"Watchdog detected critical issues: {', '.join(issues[:4])}."
    return f"Watchdog detected issues: {', '.join(issues[:4])}."


def run_watchdog() -> dict[str, Any]:
    checked_at = _now()
    issues: list[str] = []
    service_healthy = False
    command_available = False
    restart_attempted = False
    restart_reason: str | None = None
    runtime_status: dict[str, Any] = {}
    llm_status: dict[str, Any] = {}
    macro_status: dict[str, Any] = {}
    live_readiness: dict[str, Any] = {}

    try:
        health = _json_get(_health_url())
        service_healthy = bool(health and health.get("status") == "ok")
    except Exception:
        issues.append("healthz_unreachable")

    try:
        command = _json_get(_command_url())
        if command is not None:
            command_available = True
            runtime_status = dict(command.get("runtime_status", {}) or {})
            llm_status = dict(command.get("llm_status", {}) or {})
            market_snapshot = dict(command.get("market_snapshot", {}) or {})
            macro_status = dict(market_snapshot.get("macro_status", {}) or {})
            live_readiness = dict(command.get("live_readiness", {}) or {})
    except Exception:
        issues.append("command_unreachable")

    current_state = str(runtime_status.get("current_state")) if runtime_status.get("current_state") is not None else None
    current_stage = str(runtime_status.get("current_stage")) if runtime_status.get("current_stage") is not None else None
    if command_available and not current_state:
        issues.append("runtime_status_missing")
    if current_state in {"failed", "stalled"}:
        issues.append(f"runtime_{current_state}")
    if int(runtime_status.get("consecutive_failures", 0) or 0) > 0:
        issues.append("consecutive_failures_present")

    fallback_detected = bool(llm_status.get("using_mock_fallback", False))
    if fallback_detected:
        issues.append("llm_mock_fallback")

    macro_degraded = bool(macro_status.get("degraded", False))
    if macro_degraded:
        issues.append("macro_degraded")

    readiness_blockers = [str(item) for item in list(live_readiness.get("blockers", []) or [])]
    if "too_many_fallback_events" in readiness_blockers:
        issues.append("fallback_events_high")

    error_log_signal_count, error_log_excerpt = _tail_log_signals(_error_log_path())
    if error_log_signal_count >= 5:
        issues.append("error_log_signal_spike")

    severe = any(
        issue in issues
        for issue in {
            "healthz_unreachable",
            "command_unreachable",
            "runtime_failed",
            "runtime_stalled",
            "runtime_status_missing",
        }
    )
    if severe:
        restart_reason = issues[0]
        restart_attempted = _restart_service(restart_reason)

    status = "healthy"
    if issues:
        status = "critical" if severe else "warning"

    snapshot = {
        "checked_at": checked_at.isoformat(),
        "status": status,
        "summary": _snapshot_summary(status, issues),
        "service_healthy": service_healthy,
        "command_available": command_available,
        "restart_attempted": restart_attempted,
        "restart_reason": restart_reason,
        "current_state": current_state,
        "current_stage": current_stage,
        "detected_issues": issues,
        "fallback_detected": fallback_detected,
        "macro_degraded": macro_degraded,
        "llm_using_mock_fallback": bool(llm_status.get("using_mock_fallback", False)),
        "stalled_detected": current_state == "stalled",
        "error_log_signal_count": error_log_signal_count,
        "error_log_excerpt": error_log_excerpt,
    }

    history_payload = get_runtime_state_json(WATCHDOG_HISTORY_KEY) or {}
    entries = [item for item in list(history_payload.get("entries", []) or []) if isinstance(item, dict)]
    entries.append(snapshot)
    entries = entries[-72:]

    set_runtime_state_json(WATCHDOG_LATEST_KEY, snapshot, updated_at=checked_at)
    set_runtime_state_json(WATCHDOG_HISTORY_KEY, {"entries": entries}, updated_at=checked_at)
    return snapshot


def main() -> None:
    snapshot = run_watchdog()
    print(json.dumps(snapshot, ensure_ascii=False))


if __name__ == "__main__":
    main()
