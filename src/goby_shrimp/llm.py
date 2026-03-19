from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx

from .config import get_settings

logger = logging.getLogger("goby_shrimp.llm")


class MiniMaxClient:
    """MiniMax API client for structured JSON generation."""

    BASE_URL = "https://api.minimaxi.com/anthropic/v1"

    def __init__(self, api_key: str | None = None):
        settings = get_settings()
        self.api_key = api_key or settings.integrations.minimax_api_key
        self.model = settings.llm.model
        self.temperature = settings.llm.temperature
        self.max_output_tokens = settings.llm.max_output_tokens
        self.request_timeout_seconds = settings.llm.request_timeout_seconds
        if not self.api_key:
            raise ValueError("MINIMAX_API_KEY not set (env or config.integrations.minimax_api_key)")
        self.client = httpx.Client(timeout=self.request_timeout_seconds)

    def chat(
        self,
        model: str | None = None,
        system: str = "",
        user: str = "",
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        url = f"{self.BASE_URL}/messages"
        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
        }
        body = {
            "model": model or self.model or "MiniMax-M2.7",
            "system": system,
            "messages": [{"role": "user", "content": user}],
            "temperature": self.temperature if temperature is None else temperature,
            "max_tokens": self.max_output_tokens if max_tokens is None else max_tokens,
        }
        resp = self.client.post(url, headers=headers, json=body)
        resp.raise_for_status()
        data = resp.json()
        content = ""
        for block in data.get("content", []):
            if block.get("type") == "text":
                content += block.get("text", "")
        return {
            "content": content,
            "model": data.get("model"),
            "usage": data.get("usage", {}),
        }

    def chat_json(
        self,
        model: str | None = None,
        system: str = "",
        user: str = "",
        temperature: float | None = None,
    ) -> dict[str, Any]:
        result = self.chat(
            model=model,
            system=system,
            user=user + "\n\n只输出 JSON，不要其他内容。",
            temperature=self.temperature if temperature is None else temperature,
        )
        return parse_json_payload(result["content"])

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> MiniMaxClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


def parse_json_payload(text: str) -> dict[str, Any]:
    payload = text.strip()
    if "```json" in payload:
        payload = payload.split("```json", 1)[1].split("```", 1)[0]
    elif "```" in payload:
        payload = payload.split("```", 1)[1].split("```", 1)[0]
    payload = payload.strip()

    try:
        return json.loads(payload)
    except json.JSONDecodeError as first_error:
        candidates: list[str] = []
        candidates.append(payload)
        candidates.append(re.sub(r",(\s*[}\]])", r"\1", payload))

        extracted = _extract_balanced_json(payload)
        if extracted is not None:
            repaired = _repair_unescaped_inner_quotes(extracted)
            candidates.extend(
                [
                    extracted,
                    re.sub(r",(\s*[}\]])", r"\1", extracted),
                    repaired,
                    re.sub(r",(\s*[}\]])", r"\1", repaired),
                ]
            )

        for candidate in candidates:
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                continue

        logger.warning("LLM JSON parse failed: %s | payload=%s", first_error, payload[:300])
        raise


def _extract_balanced_json(text: str) -> str | None:
    start = None
    opening = ""
    closing = ""
    for index, char in enumerate(text):
        if char == "{":
            start = index
            opening, closing = "{", "}"
            break
        if char == "[":
            start = index
            opening, closing = "[", "]"
            break
    if start is None:
        return None

    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            continue
        if char == opening:
            depth += 1
        elif char == closing:
            depth -= 1
            if depth == 0:
                return text[start:index + 1]
    return None


def _repair_unescaped_inner_quotes(text: str) -> str:
    """
    修复字符串内部未转义的双引号，例如：
    "summary": "策略包含 "moving-average" 过滤"
    """
    chars: list[str] = []
    in_string = False
    escaped = False
    index = 0

    while index < len(text):
        char = text[index]
        if not in_string:
            chars.append(char)
            if char == '"':
                in_string = True
                escaped = False
            index += 1
            continue

        if escaped:
            chars.append(char)
            escaped = False
            index += 1
            continue

        if char == "\\":
            chars.append(char)
            escaped = True
            index += 1
            continue

        if char == '"':
            next_sig = _next_significant_char(text, index + 1)
            if next_sig in {",", "}", "]", ":"} or next_sig is None:
                chars.append(char)
                in_string = False
            else:
                chars.append('\\"')
            index += 1
            continue

        chars.append(char)
        index += 1

    return "".join(chars)


def _next_significant_char(text: str, start: int) -> str | None:
    for index in range(start, len(text)):
        if not text[index].isspace():
            return text[index]
    return None
