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

from ..config import mcp
from .list_episodes import parse_date_input
from src.db import get_episode_from_date

logger = logging.getLogger(__name__)


def get_episode_info_by_date(date_input: str) -> dict[str, Any] | None:
    """Get episode metadata by date.

    Args:
        date_input: Date string in various formats (YYYY-MM-DD, YYYY-MM-DDTHH:MM:SS, etc.)

    Returns:
        Episode metadata dictionary, or `None` if not found.
    """
    target_date = parse_date_input(date_input)
    if not target_date:
        return None

    episodes = get_episode_from_date(date_input)
    if episodes is None:
        return None
    return episodes[0]


@mcp.tool()
def get_episode_info(date: str) -> str:
    """Return episode metadata as JSON.

    Args:
        date: Date string in various formats (YYYY-MM-DD, YYYY-MM-DDTHH:MM:SS, etc.)

    Returns:
        JSON string with episode information (title, description, link, duration, etc.),
        or an error message.
    """
    try:
        episode_info = get_episode_info_by_date(date)
        if episode_info is None:
            return (
                f"error: no episode found for date '{date}'. please check the date format "
                "(yyyy-mm-dd) and try again."
            )

        return json.dumps(episode_info, indent=2, ensure_ascii=False)
    except Exception as exc:
        logger.error(f"Error in get_episode_info: {exc}", exc_info=True)
        return f"error retrieving episode info: {exc}"
