import os
from dotenv import load_dotenv
import logging
from src.query.config import QueryConfig
from src.query.service import PodcastQueryService
from .prompts import SERVER_PROMPT
from fastmcp import FastMCP
from fastmcp.server.auth.providers.jwt import JWTVerifier

logger = logging.getLogger(__name__)

# JWT auth setup
try:
    load_dotenv()
    public_key_path = os.getenv("JWT_PUBLIC_KEY_PATH")
    if public_key_path is None:
        raise ValueError("JWT_PUBLIC_KEY_PATH environment variable is not set.")
    with open(public_key_path, "r") as f:
        public_key = f.read()
except FileNotFoundError:
    logger.error(
        f"Public key file '{public_key_path}' not found. JWT authentication will fail."
    )
    raise
except Exception as e:
    logger.error(f"Error reading public key: {e}")
    raise

auth = JWTVerifier(
    public_key=public_key,
    issuer="urn:notpatrick:client",
    audience="urn:notpatrick:server",
    algorithm="RS256",
)

# Exported MCP instance
mcp = FastMCP(name="Rag Podcast Server", instructions=SERVER_PROMPT, auth=auth)

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


from .tools import ask_podcast, get_episode_info, get_episode_transcript, list_episodes  # noqa: E402,F401
