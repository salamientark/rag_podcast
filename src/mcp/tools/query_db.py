import logging
from ..config import mcp, get_agent
from src.query import QueryEngine, QueryConfig

logger = logging.getLogger(__name__)


@mcp.tool()
async def query_db(question: str) -> str:
    """Query the podcast database to find relevant information about podcasts, episodes, and transcripts."""
    try:
        logger.info(f"[query_db] Starting query: {question[:50]}...")

        # Use the lazy-initialized global agent instance (more efficient)
        agent = get_agent()
        logger.info("[query_db] Agent retrieved, calling agent.query()...")

        response = await agent.query(question)
        logger.info(f"[query_db] Query completed, response length: {len(str(response))}")

        return str(response)
    except Exception as e:
        logger.error(f"[query_db] Error during query: {e}", exc_info=True)
        raise
