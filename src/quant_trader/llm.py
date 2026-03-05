"""
MiniMax LLM Client

Simple client for MiniMax API (Anthropic-compatible).
Set MINIMAX_API_KEY environment variable to use.
"""
from __future__ import annotations
import json
import logging
import os
from typing import Any

import httpx

logger = logging.getLogger("quant_trader.llm")


class MiniMaxClient:
    """MiniMax API client"""

    BASE_URL = "https://api.minimaxi.com/anthropic/v1"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("MINIMAX_API_KEY", "")
        if not self.api_key:
            raise ValueError("MINIMAX_API_KEY not set")
        self.client = httpx.Client(timeout=60.0)

    def chat(
        self,
        model: str = "MiniMax-M2.5",
        system: str = "",
        user: str = "",
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> dict[str, Any]:
        """Send a chat completion request"""
        url = f"{self.BASE_URL}/messages"

        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
        }

        body = {
            "model": model,
            "system": system,
            "messages": [{"role": "user", "content": user}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        resp = self.client.post(url, headers=headers, json=body)
        resp.raise_for_status()

        data = resp.json()

        # Extract text content
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
        model: str = "MiniMax-M2.5",
        system: str = "",
        user: str = "",
        temperature: float = 0.3,
    ) -> dict[str, Any]:
        """Send request and parse JSON response"""
        # Add JSON instruction to prompt
        user_with_json = user + "\n\n只输出 JSON，不要其他内容。"

        result = self.chat(
            model=model,
            system=system,
            user=user_with_json,
            temperature=temperature,
        )

        # Parse JSON from response
        text = result["content"].strip()
        print(f"[LLM Raw] {text[:200]}...")

        # Try to extract JSON from markdown code blocks
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]

        text = text.strip()
        
        # Try parsing, fix common issues
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            # Try to fix trailing commas
            import re
            # Remove trailing commas before }
            text = re.sub(r',(\s*})', r'\1', text)
            # Remove trailing commas before ]
            text = re.sub(r',(\s*\])', r'\1', text)
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                logger.warning(f"⚠️ [LLM] JSON parse failed: {e}, text: {text[:100]}")
                raise

    def close(self):
        """Close the client"""
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def create_minimax_client(api_key: str | None = None) -> MiniMaxClient:
    """Create a MiniMax client"""
    return MiniMaxClient(api_key)
