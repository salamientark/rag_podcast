#!/usr/bin/env python3
"""
RSS Feed to Database Sync Script - Optimized Version

Based on successful simple testing. Fast and reliable.

Usage:
    uv run -m src.ingestion.sync_episodes                  # Sync last 30 days
    uv run -m src.ingestion.sync_episodes --full-sync      # Sync all episodes
    uv run -m src.ingestion.sync_episodes --limit 5        # Sync 5 episodes
    uv run -m src.ingestion.sync_episodes --dry-run        # Test mode (very fast)
"""

import argparse
import hashlib
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
import requests
from bs4 import BeautifulSoup

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.db import get_db_session, Episode

FEED_URL = "https://feedpress.me/rdvtech"


def setup_logging(verbose: bool = False) -> logging.Logger:
    """Set up logging for the sync script."""
    logger = logging.getLogger("sync_episodes")

    # Avoid adding multiple handlers
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG if verbose else logging.INFO)

    # Create logs directory if needed
    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)

    # File handler for detailed logging
    file_handler = logging.FileHandler(logs_dir / "sync_episodes.log")
    file_handler.setLevel(logging.INFO)
    file_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    # Console handler for verbose mode
    if verbose:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG)
        console_formatter = logging.Formatter("DEBUG: %(message)s")
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)

    return logger


def fetch_podcast_episodes():
    """Fetch episodes from RSS feed - proven working approach"""
    print(f"Fetching feed from {FEED_URL}...")
    try:
        response = requests.get(FEED_URL, timeout=30)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"Error fetching feed: {e}")
        return []

    # Parse XML
    soup = BeautifulSoup(response.content, "xml")
    episodes = []

    for item in soup.find_all("item"):
        episode_data = {}

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
                print(f"Could not parse date: {date_str}, error: {e}")
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

        # GUID
        guid_tag = item.find("guid")
        if guid_tag:
            episode_data["guid"] = guid_tag.get_text(strip=True)
        else:
            # Generate simple GUID from title + date
            content = f"{episode_data['title']}|{episode_data['date'].isoformat()}"
            hash_value = hashlib.md5(content.encode("utf-8")).hexdigest()[:12]
            episode_data["guid"] = f"generated-{hash_value}"

        # Only add if we have required fields
        if all(key in episode_data for key in ["title", "date", "audio_url", "guid"]):
            episodes.append(episode_data)

    print(f"Found {len(episodes)} episodes.")
    return episodes


def filter_episodes(episodes, full_sync=False, days_back=30, limit=None):
    """Filter and limit episodes"""
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


def sync_to_database(episodes, dry_run=False):
    """Sync episodes to database"""
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
                # Check if exists
                existing = (
                    session.query(Episode).filter_by(guid=episode_data["guid"]).first()
                )
                if existing:
                    print(
                        f'  - Skipped: "{episode_data["title"][:50]}..." (already exists)'
                    )
                    stats["skipped"] += 1
                else:
                    # Create new episode
                    episode = Episode(
                        guid=episode_data["guid"],
                        title=episode_data["title"],
                        published_date=episode_data["date"],
                        audio_url=episode_data["audio_url"],
                        description=episode_data.get("description", ""),
                    )
                    session.add(episode)
                    session.commit()
                    # Get the ID that was just assigned
                    session.refresh(episode)
                    print(
                        f'  ✓ Added as ID {episode.id}: "{episode_data["title"][:50]}..." ({episode_data["date"].strftime("%Y-%m-%d")})'
                    )
                    stats["added"] += 1
                    logger.info(
                        f"Added episode ID {episode.id}: {episode_data['title']}"
                    )

                stats["processed"] += 1

            except Exception as e:
                print(f'  ✗ Error: "{episode_data["title"][:50]}..." - {e}')
                logger.error(f"Error processing episode '{episode_data['title']}': {e}")
                stats["errors"] += 1

    return stats


def main():
    """Main function"""
    parser = argparse.ArgumentParser(
        description="Sync podcast episodes from RSS feed to database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  uv run -m src.ingestion.sync_episodes                  # Sync last 30 days
  uv run -m src.ingestion.sync_episodes --full-sync      # Sync all episodes
  uv run -m src.ingestion.sync_episodes --days 60        # Sync last 60 days  
  uv run -m src.ingestion.sync_episodes --limit 5        # Sync 5 most recent
  uv run -m src.ingestion.sync_episodes --limit 5 --dry-run  # Test mode (fast)
        """,
    )

    parser.add_argument(
        "--full-sync", action="store_true", help="Sync all episodes (ignores --days)"
    )
    parser.add_argument(
        "--days", type=int, default=30, help="Days back to sync (default: 30)"
    )
    parser.add_argument("--limit", type=int, help="Max episodes to process")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be synced without saving",
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Detailed console output"
    )

    args = parser.parse_args()

    # Setup logging
    logger = setup_logging(verbose=args.verbose)
    logger.info("Starting episode sync")

    try:
        # Fetch episodes
        episodes = fetch_podcast_episodes()
        if not episodes:
            print("No episodes found")
            return

        # Filter episodes
        episodes = filter_episodes(episodes, args.full_sync, args.days, args.limit)

        # Sync to database
        stats = sync_to_database(episodes, dry_run=args.dry_run)

        # Print summary
        print(
            f"\nCompleted: {stats['processed']} processed, {stats['added']} added, {stats['skipped']} skipped, {stats['errors']} errors"
        )

        if stats["errors"] > 0:
            print("Check logs/sync_episodes.log for detailed error information")

        logger.info(f"Sync completed: {stats}")
        sys.exit(0 if stats["errors"] == 0 else 1)

    except KeyboardInterrupt:
        print("\nSync interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"✗ Sync failed: {e}")
        logger.error(f"Sync failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
