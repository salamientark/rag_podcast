from ..config import mcp, get_agent


@mcp.tool()
async def query_db(question: str) -> str:
    """Query the podcast database to find relevant information about podcasts, episodes, and transcripts."""
    agent = get_agent()
    return await agent.query(question)
