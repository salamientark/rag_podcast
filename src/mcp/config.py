from fastmcp import FastMCP
from src.query.config import QueryConfig
from src.query.service import PodcastQueryService
from .prompts import SERVER_PROMPT
import logging

logger = logging.getLogger(__name__)

# Exported MCP instance
mcp = FastMCP(name="Rag Podcast Server", instructions=SERVER_PROMPT)

# Global configuration
config = QueryConfig()

# Lazy-initialized service (stateless RAG, no conversation memory)
_service_instance = None


def get_query_service() -> PodcastQueryService:
    """Get or create the global stateless PodcastQueryService instance."""
    global _service_instance
    if _service_instance is None:
        logger.info("Initializing stateless PodcastQueryService...")
        _service_instance = PodcastQueryService(config=config)
        logger.info("PodcastQueryService initialized successfully")
    return _service_instance


from .tools import query_db  # noqa
