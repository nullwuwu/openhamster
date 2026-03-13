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
        if not self.api_key:
            raise ValueError("MINIMAX_API_KEY not set (env or config.integrations.minimax_api_key)")
        self.client = httpx.Client(timeout=60.0)

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
            "model": model or self.model or "MiniMax-M2.5",
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
        payload = re.sub(r",(\s*[}\]])", r"\1", payload)
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            logger.warning("LLM JSON parse failed: %s | payload=%s", first_error, payload[:300])
            raise
