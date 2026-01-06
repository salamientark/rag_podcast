import logging

from ..config import get_query_service, mcp

logger = logging.getLogger(__name__)


@mcp.tool()
async def ask_podcast_episode(question: str, context: str) -> str:
    try:
        logger.info(f"[ask_podcast] Starting query: {question[:50]}...")

        # Use stateless query service (no conversation memory)
        service = get_query_service()
        logger.info("[ask_podcast] Service retrieved, calling service.query()...")

        response = await service.query(question, context)
        logger.info(
            f"[ask_podcast] Query completed, response length: {len(str(response))}"
        )

        return str(response)
    except Exception as e:
        logger.error(f"[ask_podcast] Error during query: {e}", exc_info=True)
        raise
