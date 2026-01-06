import logging
from ..config import mcp
from typing import Dict, Optional
from .list_episodes import fetch_db_episodes, parse_date_input
from src.db import fetch_db_episodes, Episode

logger = logging.getLogger(__name__)


def get_episode_info_by_date(date_input: str) -> Optional[Dict]:
    """
    Get episode information by date.

    Args:
        date_input: Date string in various formats (YYYY-MM-DD, YYYY-MM-DDTHH:MM:SS, etc.)

    Returns:
        Dictionary with episode information or None if not found
    """
    # Parse the input date
    target_date = parse_date_input(date_input)
    if not target_date:
        return None

    # Fetch episodes from RSS feed
    episodes = fetch_db_episodes()

    # Find episode by date (matching by date only, ignoring time)
    for episode in episodes:
        if episode.published_date.date() == target_date.date():
            # Convert datetime to ISO string for JSON serialization
            episode_copy = episode.copy()
            episode_copy.published_date = episode.published_date.isoformat()
            return episode_copy

    return None

@mcp.tool()
def get_episode_info(date: str) -> str:
    """get episode information by date.

    args:
        date: date string in various formats (yyyy-mm-dd, yyyy-mm-ddthh:mm:ss, etc.)

    returns:
        json string with episode information (title, description, link, duration, etc.) or error message.
    """
    try:
        episode_info = get_episode_info_by_date(date)

        if episode_info is None:
            return f"error: no episode found for date '{date}'. please check the date format (yyyy-mm-dd) and try again."

        # format the response as a json string
        import json

        return json.dumps(episode_info, indent=2, ensure_ascii=False)

    except Exception as e:
        return f"error retrieving episode info: {str(e)}"
