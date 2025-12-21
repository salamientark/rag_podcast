"""
MCP Tool: query_db

Stateless RAG query engine for podcast database.
The agentic behavior (query reformulation, multi-turn reasoning)
is handled by the MCP client (Claude Desktop, Node.js CLI), not by this tool.
"""

import logging
from ..config import mcp, get_query_service

logger = logging.getLogger(__name__)


@mcp.tool()
async def query_db(question: str) -> str:
    """
    Query the podcast database to find relevant information.

    This is a stateless RAG tool - each query is independent.
    The MCP client handles conversation context and query reformulation.

    Args:
        question: User's question about podcast content (in French)

    Returns:
        Relevant information from the podcast database
    """
    try:
        logger.info(f"[query_db] Starting query: {question[:50]}...")

        # Use stateless query service (no conversation memory)
        service = get_query_service()
        logger.info("[query_db] Service retrieved, calling service.query()...")

        response = await service.query(question)
        logger.info(
            f"[query_db] Query completed, response length: {len(str(response))}"
        )

        return str(response)
    except Exception as e:
        logger.error(f"[query_db] Error during query: {e}", exc_info=True)
        raise
