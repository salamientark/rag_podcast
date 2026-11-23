"""Tests for environment-driven model selection."""

import pytest

from src import model_config

GETTERS = [
    (
        model_config.get_transcription_model,
        "GEMINI_TRANSCRIPTION_MODEL",
        model_config.DEFAULT_TRANSCRIPTION_MODEL,
    ),
    (
        model_config.get_summary_model,
        "OPENAI_SUMMARY_MODEL",
        model_config.DEFAULT_SUMMARY_MODEL,
    ),
    (
        model_config.get_embedding_model,
        "VOYAGE_EMBEDDING_MODEL",
        model_config.DEFAULT_EMBEDDING_MODEL,
    ),
    (
        model_config.get_rerank_model,
        "COHERE_RERANK_MODEL",
        model_config.DEFAULT_RERANK_MODEL,
    ),
]


@pytest.fixture(autouse=True)
def _no_dotenv(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep a developer's local .env from leaking into the tests."""
    monkeypatch.setattr(model_config, "load_dotenv", lambda: False)


@pytest.mark.parametrize(("getter", "env_var", "default"), GETTERS)
def test_default_used_when_env_unset(getter, env_var, default, monkeypatch) -> None:
    monkeypatch.delenv(env_var, raising=False)
    assert getter() == default


@pytest.mark.parametrize(("getter", "env_var", "default"), GETTERS)
def test_env_overrides_default(getter, env_var, default, monkeypatch) -> None:
    monkeypatch.setenv(env_var, "  custom-model  ")
    assert getter() == "custom-model"


@pytest.mark.parametrize(("getter", "env_var", "default"), GETTERS)
def test_blank_env_falls_back_to_default(getter, env_var, default, monkeypatch) -> None:
    monkeypatch.setenv(env_var, "   ")
    assert getter() == default


def test_query_config_reads_models_from_env(monkeypatch) -> None:
    from src.query.config import QueryConfig

    monkeypatch.setenv("VOYAGE_EMBEDDING_MODEL", "voyage-test")
    monkeypatch.setenv("COHERE_RERANK_MODEL", "rerank-test")
    config = QueryConfig()
    assert config.embedding_model == "voyage-test"
    assert config.cohere_rerank_model == "rerank-test"
