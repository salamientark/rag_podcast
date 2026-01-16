#!/usr/bin/env python3
"""
RSS Feed to Database Sync Script - Optimized Version

Based on successful simple testing. Fast and reliable.

Usage:
    uv run -m src.ingestion --podcast rdv-tech              # Sync using podcast slug
    uv run -m src.ingestion --podcast "Le rendez-vous Tech" # Sync using podcast name
    uv run -m src.ingestion --podcast rdv-tech --full-sync  # Sync all episodes
    uv run -m src.ingestion --podcast rdv-tech --limit 5    # Sync 5 episodes
    uv run -m src.ingestion --podcast rdv-tech --dry-run    # Test mode (very fast)
"""

import uuid_utils as uuid
import logging
import re
import sys
from typing import Optional, Any
from datetime import datetime, timedelta
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from src.db import get_db_session, Episode
from src.logger import setup_logging, log_function


# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Init logger
logger = setup_logging(logger_name="sync_episodes", log_file="logs/sync_episodes.log")


@log_function(logger_name="sync_episodes", log_execution_time=True)
def fetch_podcast_episodes(feed_url: str) -> list[dict[str, Any]]:
    """
    Fetch episodes from an RSS feed and return parsed episode metadata.

    Parameters:
        feed_url (str): RSS feed URL to fetch (required).

    Returns:
        list[dict[str, Any]]: A list of episode dictionaries with keys:
            - uuid (str): Unique episode identifier (UUID7 format)
            - podcast (str): Podcast name extracted from the feed
            - episode_id (int): Sequential episode number within the podcast (1-based, chronological)
            - title (str): Episode title
            - date (datetime): Publication date (naive datetime)
            - audio_url (str): URL to the episode's audio file
            - description (str, optional): Cleaned episode description, up to 1000 characters

    Raises:
        ValueError: If feed_url is not provided.
    """
    if not feed_url:
        raise ValueError("feed_url is required")

    logger.info(f"Fetching feed from {feed_url}...")
    try:
        response = requests.get(feed_url, timeout=30)
        response.raise_for_status()
    except requests.RequestException as e:
        logger.error(f"Error fetching feed: {e}")
        return []

    # Parse XML
    soup = BeautifulSoup(response.content, "xml")
    episodes = []
    podcast_name = soup.find("channel").find("title").get_text(strip=True)

    for i, item in enumerate(reversed(soup.find_all("item"))):
        episode_data = {}

        # UUID/GUID
        episode_data["uuid"] = str(uuid.uuid7())

        # Podcast name
        if not podcast_name:
            continue
        episode_data["podcast"] = podcast_name

        # Episode ID (sequential)
        episode_data["episode_id"] = i + 1

        # Title
        title_tag = item.find("title")
        if not title_tag:
            continue
        episode_data["title"] = title_tag.get_text(strip=True)

        # Date
        date_tag = item.find("pubDate")
        if date_tag:
            date_str = date_tag.get_text(strip=True)
            try:
                # Remove timezone for parsing
                date_str_no_tz = " ".join(date_str.split()[:-1])
                episode_data["date"] = datetime.strptime(
                    date_str_no_tz, "%a, %d %b %Y %H:%M:%S"
                )
            except (ValueError, IndexError) as e:
                logger.error(f"Could not parse date: {date_str}, error: {e}")
                continue

        # MP3 URL (store original feedpress.me URL - works with browser headers)
        enclosure_tag = item.find("enclosure", type="audio/mpeg")
        if enclosure_tag and enclosure_tag.has_attr("url"):
            episode_data["audio_url"] = enclosure_tag["url"]
        else:
            continue

        # Description (optional)
        description_tag = item.find("description")
        if description_tag:
            # Simple text extraction
            description = description_tag.get_text(strip=True)
            # Remove HTML and clean up
            clean_desc = BeautifulSoup(description, "html.parser").get_text()
            episode_data["description"] = clean_desc[:1000]  # Limit length

        # Only add if we have required fields
        if all(
            key in episode_data
            for key in ["title", "date", "audio_url", "uuid", "episode_id", "podcast"]
        ):
            episodes.append(episode_data)

    print(f"Found {len(episodes)} episodes.")
    return episodes


def filter_episodes(
    episodes: list[dict[str, Any]],
    full_sync: bool = False,
    days_back: int = 30,
    limit: Optional[int] = None,
) -> list[dict[str, Any]]:
    """
    Filter and limit episodes based on date range and count.

    Sorts episodes chronologically (oldest first) and applies optional filtering
    by date range and limiting by count. For partial syncs, takes the most recent
    episodes; for full syncs, processes all episodes chronologically.

    Args:
        episodes: List of episode dictionaries from RSS feed
        full_sync: If True, process all episodes; if False, filter by date range
        days_back: Number of days to look back for episodes (ignored if full_sync=True)
        limit: Maximum number of episodes to process (None for no limit)

    Returns:
        Filtered and sorted list of episode dictionaries in chronological order
        (oldest first for consistent database ID assignment)
    """
    # Sort by date (oldest first) for chronological database ID assignment
    episodes.sort(key=lambda x: x["date"], reverse=False)

    # Filter by date if not full sync
    if not full_sync and days_back > 0:
        cutoff_date = datetime.now() - timedelta(days=days_back)
        episodes = [ep for ep in episodes if ep["date"] >= cutoff_date]
        print(f"Filtered to {len(episodes)} episodes from last {days_back} days")
        # Re-sort after filtering to maintain chronological order
        episodes.sort(key=lambda x: x["date"], reverse=False)

    # Apply limit (take most recent episodes, but still process in chronological order)
    if limit and limit > 0:
        if not full_sync:
            # For partial syncs, take the most recent episodes but process oldest first
            episodes = episodes[-limit:]  # Take last N episodes (most recent)
            print(
                f"Limited to {limit} most recent episodes (processed chronologically)"
            )
        else:
            # For full syncs, process all episodes chronologically
            episodes = episodes[:limit] if len(episodes) > limit else episodes
            print(
                f"Limited to {limit} episodes from the beginning (chronological order)"
            )

    return episodes


def generate_slug(name: str) -> str:
    """Generate a URL-friendly slug from a podcast name."""
    slug = name.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug


@log_function(logger_name="sync_episodes", log_execution_time=True)
def sync_to_database(
    episodes: list[dict[str, Any]], podcast_id: int, dry_run: bool = False
) -> dict[str, int]:
    """
    Persist a list of parsed podcast episodes to the database, optionally performing a dry run.

    Processes episodes in the provided order (chronological: oldest first). When an episode with the same (podcast_id, audio_url) combination already exists, that episode is skipped. In dry-run mode, no database changes are made and a summary of actions is printed.

    Parameters:
        episodes (list[dict[str, Any]]): Episode dictionaries with required keys:
            - uuid: UUID for the episode
            - episode_id: Sequential episode number for the podcast
            - title: Episode title
            - date: Publication datetime
            - audio_url: URL to the episode audio
          Optional keys:
            - description: Episode description
        podcast_id (int): The podcast FK ID to associate episodes with.
        dry_run (bool): If True, print what would be performed without modifying the database.

    Returns:
        dict[str, int]: Statistics for the operation:
            - processed: Number of episodes inspected
            - added: Number of new episodes inserted
            - skipped: Number of episodes skipped because they already existed
            - errors: Number of episodes that failed to process
    """
    logger = logging.getLogger("sync_episodes")

    if not episodes:
        print("No episodes to process")
        return {"processed": 0, "added": 0, "skipped": 0, "errors": 0}

    print(f"Processing {len(episodes)} episodes (chronological order: oldest first)...")

    if dry_run:
        print("DRY RUN - Episodes that would be processed (oldest to newest):")
        for i, ep in enumerate(episodes, 1):
            print(
                f'  ✓ Would add as ID {i}: "{ep["title"][:60]}..." ({ep["date"].strftime("%Y-%m-%d")})'
            )
            print(f"    URL: {ep['audio_url'][:80]}...")
        return {
            "processed": len(episodes),
            "added": len(episodes),
            "skipped": 0,
            "errors": 0,
        }

    stats = {"processed": 0, "added": 0, "skipped": 0, "errors": 0}

    with get_db_session() as session:
        for episode_data in episodes:
            try:
                # Check if exists by podcast_id and audio_url
                existing = (
                    session.query(Episode)
                    .filter_by(
                        podcast_id=podcast_id,
                        audio_url=episode_data["audio_url"],
                    )
                    .first()
                )
                if existing:
                    stats["skipped"] += 1
                else:
                    # Create new episode with podcast_id FK
                    episode = Episode(
                        uuid=episode_data["uuid"],
                        podcast_id=podcast_id,
                        episode_id=episode_data["episode_id"],
                        title=episode_data["title"],
                        published_date=episode_data["date"],
                        audio_url=episode_data["audio_url"],
                        description=episode_data.get("description", ""),
                        processing_stage="synced",
                    )
                    session.add(episode)
                    session.commit()
                    # Get the ID that was just assigned
                    session.refresh(episode)
                    print(
                        f'  ✓ Added as ID {episode.episode_id}: "{episode_data["title"][:50]}..." ({episode_data["date"].strftime("%Y-%m-%d")})'
                    )
                    stats["added"] += 1
                    logger.info(
                        f"Added episode ID {episode.episode_id}: {episode_data['title']}"
                    )

                stats["processed"] += 1

            except Exception as e:
                session.rollback()
                print(f'  ✗ Error: "{episode_data["title"][:50]}..." - {e}')
                logger.error(f"Error processing episode '{episode_data['title']}': {e}")
                stats["errors"] += 1

    return stats
