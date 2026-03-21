from __future__ import annotations

from pathlib import Path

from openhamster.config.settings import load_app_settings


def test_settings_source_priority(tmp_path: Path, monkeypatch) -> None:
    base = tmp_path / "base.yaml"
    local = tmp_path / "local.yaml"

    base.write_text(
        """
app_name: OpenHamster
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


def test_settings_load_env_file_before_process_env(tmp_path: Path, monkeypatch) -> None:
    base = tmp_path / "base.yaml"
    local = tmp_path / "local.yaml"
    env_file = tmp_path / ".env"
    env_local_file = tmp_path / ".env.local"

    base.write_text("app_name: OpenHamster\n", encoding="utf-8")
    local.write_text("", encoding="utf-8")
    env_file.write_text(
        'MINIMAX_API_KEY="from-dotenv"\nLLM_PROVIDER=mock\n',
        encoding="utf-8",
    )
    env_local_file.write_text(
        "LLM_PROVIDER=minimax\n",
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LLM_MODEL", "MiniMax-M2.5")

    settings, source_map = load_app_settings(base_path=base, local_path=local)

    assert settings.integrations.minimax_api_key == "from-dotenv"
    assert settings.llm.provider == "minimax"
    assert settings.llm.model == "MiniMax-M2.5"
    assert source_map["integrations.minimax_api_key"] == "env_file"
    assert source_map["llm.provider"] == "env_file"
    assert source_map["llm.model"] == "env"
