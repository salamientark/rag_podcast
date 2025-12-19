from ..config import mcp, get_agent
from src.query import QueryEngine, QueryConfig


@mcp.tool()
async def query_db(question: str) -> str:
    """Query the podcast database to find relevant information about podcasts, episodes, and transcripts."""
    # agent = get_agent()
    # return await agent.query(question)

    # Init agent
    config = QueryConfig()
    engine = QueryEngine(config)

    response = engine.query_engine.query(question)

    return str(response)
