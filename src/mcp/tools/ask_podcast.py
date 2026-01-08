"""MCP Tool: ask_podcast

Stateless RAG query engine for podcast database.
The agentic behavior (query reformulation, multi-turn reasoning)
is handled by the MCP client (Claude Desktop, Node.js CLI), not by this tool.
"""

import logging

from ..config import get_query_service, mcp
from ..prompts import ALLOWED_PODCASTS

logger = logging.getLogger(__name__)


@mcp.tool("ask_podcast")
async def ask_podcast(question: str, podcast: str | None = None) -> str:
    """Ask a general question about podcast content.

    This is a stateless RAG tool - each query is independent.
    The MCP client handles conversation context and query reformulation.

    Args:
        question: User's question about podcast content (in French)
        podcast: Optional podcast name to filter results (must match one of the accepted podcast names exactly)

    Returns:
        Relevant information from the podcast database
    """
    try:
        normalized_podcast = (podcast or "").strip() or None

        if (
            normalized_podcast is not None
            and normalized_podcast not in ALLOWED_PODCASTS
        ):
            accepted = " | ".join(sorted(ALLOWED_PODCASTS))
            return f"Podcast invalide. Noms acceptés (exactement): {accepted}."

        logger.info(
            f"[ask_podcast] Starting query: {question[:50]}... (podcast={normalized_podcast!r})"
        )

        # Use stateless query service (no conversation memory)
        service = get_query_service()
        logger.info("[ask_podcast] Service retrieved, calling service.query()...")

        response = await service.query(question, podcast=normalized_podcast)
        logger.info(
            f"[ask_podcast] Query completed, response length: {len(str(response))}"
        )

        return str(response)
    except Exception as e:
        logger.error(f"[ask_podcast] Error during query: {e}", exc_info=True)
        raise
