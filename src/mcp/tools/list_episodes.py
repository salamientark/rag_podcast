import json
import logging
from datetime import datetime, timedelta, date
from typing import Dict, List, Optional

from src.db import get_episode_from_date

from ..config import mcp
from ..prompts import ALLOWED_PODCASTS

logger = logging.getLogger(__name__)


def parse_date_input(date_input: str) -> Optional[datetime]:
    """Parse various date input formats into a datetime object."""
    # Common date formats to try
    date_formats = [
        "%Y-%m-%d",  # 2025-07-08
        "%Y-%m-%dT%H:%M:%S",  # 2025-07-08T07:00:00
        "%d/%m/%Y",  # 08/07/2025
        "%d-%m-%Y",  # 08-07-2025
        "%Y/%m/%d",  # 2025/07/08
    ]

    for fmt in date_formats:
        try:
            return datetime.strptime(date_input, fmt)
        except ValueError:
            continue

    return None


def list_episodes_in_range(podcast: str, start_date_str: str) -> List[Dict[str, str]]:
    """List podcast episodes starting from a given date.

    - If a valid start date is provided, returns up to 12 months from that date.
    - If start date is empty or invalid, returns ALL episodes for the podcast.
    """
    parsed_start = parse_date_input(start_date_str)

    if parsed_start:
        start_date = parsed_start.date()
        end_date = start_date + timedelta(days=365)
    else:
        # No valid date: return all episodes from the very beginning
        start_date = date(2000, 1, 1)
        end_date = datetime.now().date() + timedelta(days=1)

    total_days = (end_date - start_date).days
    episodes = get_episode_from_date(date.isoformat(start_date), days=total_days) or []
    episodes = [episode for episode in episodes if episode.get("podcast") == podcast]

    filtered_episodes: list[dict[str, str]] = []
    for episode in episodes:
        episode_date = datetime.fromisoformat(episode["published_date"]).date()
        if start_date <= episode_date <= end_date:
            filtered_episodes.append(
                {
                    "episode_name": episode["title"],
                    "date": episode_date.isoformat(),
                }
            )

    # Sort by date ascending
    filtered_episodes.sort(key=lambda episode: episode["date"])

    return filtered_episodes


@mcp.tool()
def list_episodes(beginning: str, podcast: str) -> str:
    """List podcast episodes starting from a given date for up to 12 months.

    Args:
        beginning: Start date (e.g., "YYYY-MM-DD"). If empty or invalid, returns ALL episodes for the podcast (useful for finding the first/oldest episode).
        podcast: Podcast name (must match one of the accepted podcast names exactly).

    Returns:
        JSON string with a list of episodes, each containing 'episode_name' and 'date', sorted by date ascending (oldest first).
    """
    normalized_podcast = podcast.strip()
    logger.info(f"Listing episodes for podcast: {normalized_podcast} from {beginning}")
    if normalized_podcast not in ALLOWED_PODCASTS:
        accepted = " | ".join(sorted(ALLOWED_PODCASTS))
        return f"Podcast invalide. Noms acceptés (exactement): {accepted}."

    try:
        episodes = list_episodes_in_range(
            podcast=normalized_podcast,
            start_date_str=beginning,
        )
        logger.info(f"Found {len(episodes)} episodes for podcast: {normalized_podcast}")
        return json.dumps(episodes, indent=2, ensure_ascii=False)
    except ValueError as exc:
        logger.error(f"ValueError in list_episodes: {exc}", exc_info=True)
        return f"Erreur lors de la liste des épisodes : {exc}"
    except Exception as exc:
        logger.error(f"Unexpected error in list_episodes: {exc}", exc_info=True)
        return (
            "Une erreur inattendue s'est produite lors de la liste des épisodes : "
            f"{exc}"
        )
