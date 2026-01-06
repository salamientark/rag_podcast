"""MCP Tool: ask_podcast

Stateless RAG query engine for podcast database.
The agentic behavior (query reformulation, multi-turn reasoning)
is handled by the MCP client (Claude Desktop, Node.js CLI), not by this tool.
"""

import logging

from ..config import get_query_service, mcp

logger = logging.getLogger(__name__)


@mcp.tool("ask_podcast")
async def ask_podcast(question: str) -> str:
    """Ask a general question about podcast content.

    This is a stateless RAG tool - each query is independent.
    The MCP client handles conversation context and query reformulation.

    Args:
        question: User's question about podcast content (in French)

    Returns:
        Relevant information from the podcast database
    """
    try:
        logger.info(f"[ask_podcast] Starting query: {question[:50]}...")

        # Use stateless query service (no conversation memory)
        service = get_query_service()
        logger.info("[ask_podcast] Service retrieved, calling service.query()...")

        response = await service.query(question)
        logger.info(
            f"[ask_podcast] Query completed, response length: {len(str(response))}"
        )

        return str(response)
    except Exception as e:
        logger.error(f"[ask_podcast] Error during query: {e}", exc_info=True)
        raise
