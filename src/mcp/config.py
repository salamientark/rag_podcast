from fastmcp import FastMCP
from src.query.config import QueryConfig
from src.query.agent import PodcastQueryAgent
from .prompts import SERVER_PROMPT
import logging

logger = logging.getLogger(__name__)

# Exported MCP instance
mcp = FastMCP(name="Rag Podcast Server", instructions=SERVER_PROMPT)

# Global configuration
config = QueryConfig()

# Lazy-initialized agent (prevents startup blocking)
_agent_instance = None


def get_agent() -> PodcastQueryAgent:
    """Get or create the global PodcastQueryAgent instance."""
    global _agent_instance
    if _agent_instance is None:
        logger.info("Initializing PodcastQueryAgent...")
        _agent_instance = PodcastQueryAgent(config=config)
        logger.info("PodcastQueryAgent initialized successfully")
    return _agent_instance


from .tools import query_db  #noqa
