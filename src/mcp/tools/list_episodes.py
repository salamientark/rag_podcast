import logging
from ..config import mcp
from src.db import get_db_session, Episode
from typing import List, Dict, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


def fetch_db_episodes() -> list[Episode]:
    """Fetch all episodes from the database.

    Returns:
        List of Episode objects from the database, sorted by published date descending.
    """
    logger = logging.getLogger("pipeline")
    logger.info("Fetching episodes from database...")
    with get_db_session() as session:
        episodes = session.query(Episode).order_by(Episode.published_date.desc()).all()
    logger.info(f"Fetched {len(episodes)} episodes from database.")
    return episodes


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


def list_episodes_in_range(start_date_str: str) -> List[Dict[str, str]]:
    """
    Lists podcast episodes starting from a given date.
    - The range is up to 12 months from the start date.
    - If start date is invalid, it defaults to 3 months ago.
    """
    three_months_ago = datetime.now().date() - timedelta(days=30)

    # Determine start date
    parsed_start = parse_date_input(start_date_str)
    start_date = parsed_start.date() if parsed_start else three_months_ago

    # Determine end date: 12 months after start, capped at 3 months ago
    end_date = start_date + timedelta(days=365)

    if start_date > end_date:
        return []

    all_episodes = fetch_db_episodes()

    filtered_episodes = []
    for episode in all_episodes:
        episode_date = episode.published_date.date()
        if start_date <= episode_date <= end_date:
            filtered_episodes.append(
                {
                    "episode_name": episode.title,
                    "date": episode_date.isoformat(),
                }
            )

    # Sort by date ascending
    filtered_episodes.sort(key=lambda e: e["date"])

    return filtered_episodes


@mcp.tool()
def list_episodes(beginning: str) -> str:
    """List podcast episodes starting from a given date for up to 12 months.
    The results are capped at 3 months before the current date.

    Args:
        beginning: Required start date (e.g., "YYYY-MM-DD"). If the date is invalid, it defaults to 3 months ago.

    Returns:
        JSON string with a list of episodes, each containing 'episode_name' and 'date', sorted by date.
    """
    try:
        episodes = list_episodes_in_range(start_date_str=beginning)

        import json

        return json.dumps(episodes, indent=2, ensure_ascii=False)

    except ValueError as e:
        return f"Error listing episodes: {str(e)}"
    except Exception as e:
        return f"An unexpected error occurred while listing episodes: {str(e)}"

