import logging
from ..config import mcp
from src.query.service import PodcastQueryService
from src.query.config import QueryConfig

logger = logging.getLogger(__name__)

# Lazy-initialized stateless query service (no conversation memory)
_query_service = None


def get_query_service() -> PodcastQueryService:
    """Get or create the global stateless PodcastQueryService instance."""
    global _query_service
    if _query_service is None:
        logger.info("Initializing stateless PodcastQueryService...")
        config = QueryConfig()
        _query_service = PodcastQueryService(config)
        logger.info("PodcastQueryService initialized successfully")
    return _query_service


@mcp.tool()
async def query_db(question: str) -> str:
    """Query the podcast database to find relevant information about podcasts, episodes, and transcripts."""
    try:
        logger.info(f"[query_db] Starting query: {question[:50]}...")

        # Use stateless query service (no conversation memory between calls)
        service = get_query_service()
        logger.info("[query_db] Service retrieved, calling service.query()...")

        response = await service.query(question)
        logger.info(f"[query_db] Query completed, response length: {len(str(response))}")

        return str(response)
    except Exception as e:
        logger.error(f"[query_db] Error during query: {e}", exc_info=True)
        raise
