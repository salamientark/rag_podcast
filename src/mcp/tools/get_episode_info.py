"""MCP tool: `get_episode_info`.

This tool queries the PostgreSQL database to retrieve episode *metadata* (title,
description, duration, link, etc.) for a given date.

Important:
- This tool does NOT search within episode content/transcripts.
- For questions about what is said inside episodes, use:
  - `ask_podcast` for multi-episode content search
  - `get_episode_transcript` for a specific episode (by date)
"""

import json
import logging
from typing import Any

from src.db import get_episode_from_date

from ..config import mcp
from ..prompts import ALLOWED_PODCASTS
from .list_episodes import parse_date_input

logger = logging.getLogger(__name__)


def get_episode_info_by_date(date_input: str, podcast: str) -> dict[str, Any] | None:
    """Get episode metadata by date and podcast.

    Args:
        date_input: Date string in various formats (YYYY-MM-DD, YYYY-MM-DDTHH:MM:SS, etc.)
        podcast: Podcast name (must match one of the accepted podcast names exactly).

    Returns:
        Episode metadata dictionary, or `None` if not found.
    """
    target_date = parse_date_input(date_input)
    if not target_date:
        return None

    query_date = target_date.date().isoformat()
    episodes = get_episode_from_date(query_date) or []

    normalized_podcast = podcast.strip()
    for episode in episodes:
        if episode.get("podcast") == normalized_podcast:
            return episode

    return None


@mcp.tool()
def get_episode_info(date: str, podcast: str) -> str:
    """Return episode metadata as JSON.

    Args:
        date: Date string in various formats (YYYY-MM-DD, YYYY-MM-DDTHH:MM:SS, etc.)
        podcast: Podcast name (must match one of the accepted podcast names exactly).

    Returns:
        JSON string with episode information (title, description, link, duration, etc.),
        or an error message.
    """
    try:
        normalized_podcast = podcast.strip()
        if normalized_podcast not in ALLOWED_PODCASTS:
            accepted = " | ".join(sorted(ALLOWED_PODCASTS))
            return f"Podcast invalide. Noms acceptés (exactement): {accepted}."

        episode_info = get_episode_info_by_date(date, normalized_podcast)
        if episode_info is None:
            return (
                f"error: no episode found for date '{date}' and podcast '{normalized_podcast}'. "
                "please check the date format (yyyy-mm-dd) and try again."
            )

        return json.dumps(episode_info, indent=2, ensure_ascii=False)
    except Exception as exc:
        logger.error(f"Error in get_episode_info: {exc}", exc_info=True)
        return f"error retrieving episode info: {exc}"
