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


def test_parse_json_payload_repairs_unescaped_quotes_inside_string() -> None:
    payload = """
    {
      "stance_for": ["策略包含 "moving-average" 过滤，顺势特征明确"],
      "stance_against": ["回撤仍可能偏大"],
      "synthesis": "可继续观察"
    }
    """
    parsed = parse_json_payload(payload)
    assert parsed["stance_for"][0] == '策略包含 "moving-average" 过滤，顺势特征明确'
