"""MCP tool: `ask_podcast_episode`.

This tool queries the Qdrant vector database (semantic search over episode
transcripts/content) but takes an explicit `context` string to focus the query
on a particular episode.

Use it when:
- A user asks for precise information from the content of a specific episode.

The `context` should be built from PostgreSQL metadata tools like `list_episodes`
and/or `get_episode_info`, and formatted like:

    "Title: ..., description: ..., duration: ..."

Include whatever metadata is available.
"""

import logging

from ..config import get_query_service, mcp

logger = logging.getLogger(__name__)


@mcp.tool()
async def ask_podcast_episode(question: str, context: str) -> str:
    """Answer a question about a specific episode using contextual metadata.

    Args:
        question: The user's question.
        context: Metadata context string (title/description/duration/etc.).

    Returns:
        A French answer based on transcript semantic search.

    Raises:
        Exception: Re-raises any unexpected runtime errors.
    """
    try:
        logger.info(f"[ask_podcast_episode] Starting query: {question[:50]}...")

        service = get_query_service()
        logger.info(
            "[ask_podcast_episode] Service retrieved, calling service.query()..."
        )

        response = await service.query(question, context)
        logger.info(
            f"[ask_podcast_episode] Query completed, response length: {len(str(response))}"
        )

        return str(response)
    except Exception as exc:
        logger.error(f"[ask_podcast_episode] Error during query: {exc}", exc_info=True)
        raise
