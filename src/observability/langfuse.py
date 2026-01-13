"""Langfuse + OpenInference observability utilities.

This project uses an MCP server as the gateway into the RAG pipeline.

We initialize Langfuse once at process startup (in `src/mcp/config.py`) and
optionally instrument LlamaIndex via OpenInference. Individual tool calls then
create traces/spans that are exported to Langfuse Cloud.

Design goals:
- Never block or crash the app if Langfuse is misconfigured.
- Keep instrumentation lightweight and centralized.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from openinference.instrumentation.llama_index import LlamaIndexInstrumentor
from langfuse import get_client

logger = logging.getLogger(__name__)

_INITIALIZED = False


def _is_langfuse_configured() -> bool:
    return bool(os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"))


def init_langfuse_observability() -> bool:
    """Initialize Langfuse client and instrument LlamaIndex.

    Returns:
        True if Langfuse appears configured and initialization succeeded.
        False if Langfuse is not configured or initialization fails.
    """

    global _INITIALIZED
    if _INITIALIZED:
        return True

    if not _is_langfuse_configured():
        logger.warning(
            "Langfuse keys not configured (LANGFUSE_PUBLIC_KEY/LANGFUSE_SECRET_KEY); tracing disabled."
        )
        return False

    langfuse = get_client()

    try:
        if not langfuse.auth_check():
            logger.error(
                "Langfuse auth check failed; verify LANGFUSE_* environment variables."
            )
            return False
    except Exception as exc:
        logger.error(f"Langfuse initialization failed: {exc}")
        return False

    try:
        LlamaIndexInstrumentor().instrument()
        logger.info("OpenInference LlamaIndex instrumentation enabled")
    except Exception as exc:
        # Instrumentation is optional; core tracing still works.
        logger.warning(f"Failed to instrument LlamaIndex via OpenInference: {exc}")

    _INITIALIZED = True
    return True


def get_langfuse() -> Any:
    """Return the singleton Langfuse client.

    Note: This does not guarantee Langfuse is configured; call
    `init_langfuse_observability()` during startup.
    """

    return get_client()
