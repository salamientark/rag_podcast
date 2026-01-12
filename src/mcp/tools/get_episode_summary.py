"""MCP tool: `get_episode_summary`.

This tool retrieves an episode transcript (by date) and returns a structured summary.

Data sources:
- PostgreSQL: episode metadata (used to locate `formatted_transcript_path`)
- Object storage / local filesystem: transcript file retrieval
- OpenAI: generates the summary from transcript text

Use it when:
- A user asks for a summary of a specific episode (by date, or after you determine the date).

For content questions across multiple episodes, use `ask_podcast`.
"""

import logging
from typing import Optional
from urllib.parse import urlparse

from src.storage.cloud import get_cloud_storage

from ..config import mcp
from ..prompts import ALLOWED_PODCASTS
from .get_episode_info import get_episode_info_by_date

logger = logging.getLogger(__name__)


@mcp.tool()
async def get_episode_summary(
    date: str, podcast: str, language: Optional[str] = "en"
) -> str:
    """Return a structured summary for the episode published on the given date.

    Args:
        date: Date string in various formats (YYYY-MM-DD, YYYY-MM-DDTHH:MM:SS, etc.).
        podcast: Podcast name (must match one of the accepted podcast names exactly).
        language: Output language (ISO-ish, e.g. "fr", "en"). Defaults to "en".

    Returns:
        Markdown summary text, or an error message.

    Raises:
        Exception: Re-raises any unexpected runtime errors.
    """
    try:
        normalized_podcast = podcast.strip()
        if normalized_podcast not in ALLOWED_PODCASTS:
            accepted = " | ".join(sorted(ALLOWED_PODCASTS))
            return f"Podcast invalide. Noms acceptés (exactement): {accepted}."

        logger.info(
            f"[get_episode_summary] Looking for episode published on {date} (podcast={normalized_podcast})..."
        )

        episode_info = get_episode_info_by_date(date, normalized_podcast)
        if episode_info is None:
            return (
                f"error: no episode found for date '{date}' and podcast '{normalized_podcast}'. "
                "please check the date format (yyyy-mm-dd) and try again."
            )

        # Get summary
        storage_engine = get_cloud_storage()
        client = storage_engine.get_client()
        summary_url = episode_info.get("summary_path")
        if summary_url is None:
            return f"error: no summary found for episode on '{date}' for podcast '{normalized_podcast}'."
        parsed_url = urlparse(summary_url)
        bucket_name = storage_engine.bucket_name
        key = parsed_url.path.lstrip("/").split("/", 1)[1]
        response = client.get_object(Bucket=bucket_name, Key=key)
        summary_content = response["Body"].read().decode("utf-8")
        return summary_content

    except Exception as exc:
        logger.error(
            f"[get_episode_summary] Error during episode summarization: {exc}",
            exc_info=True,
        )
        raise
