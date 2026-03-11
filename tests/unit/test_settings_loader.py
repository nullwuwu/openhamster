from __future__ import annotations

from pathlib import Path

from quant_trader.config.settings import load_app_settings


def test_settings_source_priority(tmp_path: Path, monkeypatch) -> None:
    base = tmp_path / "base.yaml"
    local = tmp_path / "local.yaml"

    base.write_text(
        """
app_name: quant-trader
storage:
  database_url: sqlite:///base.db
data_source:
  provider: akshare
""".strip(),
        encoding="utf-8",
    )
    local.write_text(
        """
storage:
  database_url: sqlite:///local.db
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setenv("DATABASE_URL", "sqlite:///env.db")

    settings, source_map = load_app_settings(base_path=base, local_path=local)

    assert settings.storage.database_url == "sqlite:///env.db"
    assert source_map["storage.database_url"] == "env"
    assert source_map["data_source.provider"] == "base"
