"""MCP Tool: ask_podcast

Stateless RAG query engine for podcast database.
The agentic behavior (query reformulation, multi-turn reasoning)
is handled by the MCP client (Claude Desktop, Node.js CLI), not by this tool.
"""

import contextlib
import logging

from src.db import get_podcast_by_name_or_slug, get_podcasts
from src.observability.langfuse import get_langfuse

from ..config import get_query_service, mcp

logger = logging.getLogger(__name__)


@mcp.tool("ask_podcast")
async def ask_podcast(question: str, podcast: str | None = None) -> str:
    """Ask a general question about podcast content.

    This is a stateless RAG tool - each query is independent.
    The MCP client handles conversation context and query reformulation.

    Args:
        question: User's question about podcast content (in French)
        podcast: Optional podcast name or slug to filter results. If omitted, searches all podcasts.

    Returns:
        Relevant information from the podcast database
    """
    try:
        normalized_podcast = (podcast or "").strip() or None
        resolved_podcast_name: str | None = None

        if normalized_podcast is not None:
            # Resolve name or slug to canonical podcast name
            podcast_obj = get_podcast_by_name_or_slug(normalized_podcast)
            if podcast_obj is None:
                available = get_podcasts()
                available_str = (
                    " | ".join(sorted(available)) if available else "(aucun)"
                )
                return f"Podcast '{normalized_podcast}' non trouvé. Podcasts disponibles: {available_str}."
            resolved_podcast_name = podcast_obj.name

        logger.info(
            f"[ask_podcast] Starting query: {question[:50]}... (podcast={resolved_podcast_name!r})"
        )

        # Use stateless query service (no conversation memory)
        service = get_query_service()
        logger.info("[ask_podcast] Service retrieved, calling service.query()...")

        langfuse = get_langfuse()
        try:
            observation_cm = langfuse.start_as_current_observation(
                as_type="span", name="mcp.ask_podcast"
            )
        except Exception as exc:
            logger.debug(f"[ask_podcast] Langfuse observation start failed: {exc}")
            observation_cm = contextlib.nullcontext()

        with observation_cm as observation:
            if observation is not None:
                try:
                    observation.update(
                        input={"question": question, "podcast": resolved_podcast_name},
                        metadata={"tool": "ask_podcast"},
                    )
                except Exception as exc:
                    logger.debug(
                        f"[ask_podcast] Langfuse observation update failed: {exc}"
                    )

            response = await service.query(question, podcast=resolved_podcast_name)

            if observation is not None:
                try:
                    observation.update(output=str(response))
                except Exception as exc:
                    logger.debug(
                        f"[ask_podcast] Langfuse observation close failed: {exc}"
                    )

        logger.info(
            f"[ask_podcast] Query completed, response length: {len(str(response))}"
        )
        return str(response)
    except Exception as e:
        logger.error(f"[ask_podcast] Error during query: {e}", exc_info=True)
        raise
