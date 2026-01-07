"""MCP tool: `ask_podcast_episode`.

This tool queries the Qdrant vector database (semantic search over episode
transcripts/content) but takes an explicit `context` string to focus the query
on a particular episode.

Use it when:
- A user asks for precise information from the content of a specific episode.

The `context` should be built from PostgreSQL metadata tools like `list_episodes`
and/or `get_episode_info`, and formatted like:

    "Title: ..., description: ..., duration: ..."

Include whatever metadata is available.
"""

import logging
import os

from ..config import get_query_service, mcp
from .get_episode_info import get_episode_info_by_date
from src.storage.cloud import cloudStorage

logger = logging.getLogger(__name__)


async def fetch_transcript(transcript_link: str) -> str:
    """Fetch the transcript from the given link.
    Args:
        transcript_link (str): The URL to the transcript.

    Returns:
        str: The content of the transcript.
    """
    try:
        storage_engine = cloudStorage()
        client = storage_engine.get_client()
        client.download_file(transcript_link, "temp_transcript.txt")

        content = ""
        with open("temp_transcript.txt", "r") as file:
            content = file.read()
        os.remove("temp_transcript.txt")
        return content

    except Exception as exc:
        logger.error(f"[fetch_transxript] Error during transxript fetch: {exc}", exc_info=True)
        raise




@mcp.tool()
async def get_episode_transcript(date: str) -> str:
    """Return the episode transcript bases on provided date.

    Args:
        date_input: Date string in various formats (YYYY-MM-DD, YYYY-MM-DDTHH:MM:SS, etc.)

    Returns:
        A French transcript of the episode

    Raises:
        Exception: Re-raises any unexpected runtime errors.
    """
    try:
        logger.info(f"[get_episode_transcript] looking for episode publised in {date}...")

        episode_info = get_episode_info_by_date(date)
        if episode_info is None:
            return (
                f"error: no episode found for date '{date}'. please check the date format "
                "(yyyy-mm-dd) and try again."
            )

        transcript_link = episode_info.get("transcript_link")
        if not transcript_link:
            return f"error: no transcript found for episode on date '{date}'."

        transcript_content = fetch_transcript(transcript_link)
        return transcript_content

    except Exception as exc:
        logger.error(f"[ask_podcast_episode] Error during query: {exc}", exc_info=True)
        raise
