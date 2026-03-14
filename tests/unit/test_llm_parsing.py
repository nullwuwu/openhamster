from __future__ import annotations

from goby_shrimp.llm import parse_json_payload


def test_parse_json_payload_extracts_wrapped_json_object() -> None:
    payload = """
    Here is the result:

    {
      "ok": true,
      "provider": "minimax"
    }

    Use it carefully.
    """
    parsed = parse_json_payload(payload)
    assert parsed["ok"] is True
    assert parsed["provider"] == "minimax"
