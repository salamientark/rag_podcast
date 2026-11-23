"""Model names used by the backend, overridable through environment variables.

Each getter reads its variable at call time, so a value set in `.env` is picked
up no matter when the calling module was imported. An unset or blank variable
falls back to the default below.

| Variable                     | Used for                       |
|------------------------------|--------------------------------|
| GEMINI_TRANSCRIPTION_MODEL   | Audio transcription (Gemini)   |
| OPENAI_SUMMARY_MODEL         | Episode summaries (OpenAI)     |
| VOYAGE_EMBEDDING_MODEL       | Chunk and query embeddings     |
| COHERE_RERANK_MODEL          | Reranking of retrieved chunks  |
"""

import os

from dotenv import load_dotenv

DEFAULT_TRANSCRIPTION_MODEL = "gemini-3-flash-preview"
DEFAULT_SUMMARY_MODEL = "gpt-5.2"
DEFAULT_EMBEDDING_MODEL = "voyage-3.5"
DEFAULT_RERANK_MODEL = "rerank-v3.5"


def _resolve(env_var: str, default: str) -> str:
    """
    Read a model name from the environment.

    Args:
        env_var: Name of the environment variable to read.
        default: Model name returned when the variable is unset or blank.

    Returns:
        The configured model name, stripped of surrounding whitespace.
    """
    load_dotenv()
    return os.getenv(env_var, "").strip() or default


def get_transcription_model() -> str:
    """
    Get the Gemini model used to transcribe episode audio.

    Returns:
        The model name from GEMINI_TRANSCRIPTION_MODEL, or the default.
    """
    return _resolve("GEMINI_TRANSCRIPTION_MODEL", DEFAULT_TRANSCRIPTION_MODEL)


def get_summary_model() -> str:
    """
    Get the OpenAI model used to summarize transcripts.

    Returns:
        The model name from OPENAI_SUMMARY_MODEL, or the default.
    """
    return _resolve("OPENAI_SUMMARY_MODEL", DEFAULT_SUMMARY_MODEL)


def get_embedding_model() -> str:
    """
    Get the Voyage AI model used to embed chunks and queries.

    Vectors from different embedding models are not comparable: changing this
    means re-embedding every episode already stored in Qdrant, and the new
    model must produce the collection's vector size (1024). The model must
    also have an entry in `VOYAGE_LIMITS` (src/chunker/token_counter.py),
    otherwise embedding fails with "Unknown Voyage AI model".

    Returns:
        The model name from VOYAGE_EMBEDDING_MODEL, or the default.
    """
    return _resolve("VOYAGE_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL)


def get_rerank_model() -> str:
    """
    Get the Cohere model used to rerank retrieved chunks.

    Returns:
        The model name from COHERE_RERANK_MODEL, or the default.
    """
    return _resolve("COHERE_RERANK_MODEL", DEFAULT_RERANK_MODEL)
