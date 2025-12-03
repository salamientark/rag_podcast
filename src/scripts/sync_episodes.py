#!/usr/bin/env python3
"""
RSS Feed to Database Sync Script

Fetches episode information from the RSS feed and saves it to the database,
avoiding duplicates and handling missing GUIDs gracefully.

Usage:
    python src/scripts/sync_episodes.py                    # Sync last 30 days
    python src/scripts/sync_episodes.py --full-sync        # Sync all episodes
    python src/scripts/sync_episodes.py --days 60          # Sync last 60 days
    python src/scripts/sync_episodes.py --limit 5 --dry-run # Test mode
"""

import argparse
import hashlib
import logging
import re
import sys
import requests
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from bs4 import BeautifulSoup

# Add project root to path for imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

try:
    from src.db import get_db_session, Episode
except ImportError as e:
    print(f"Import error: {e}")
    print("Make sure you're running from the project root directory")
    sys.exit(1)


FEED_URL = "https://feedpress.me/rdvtech"


def fetch_podcast_episodes() -> List[Dict]:
    """Fetches and parses the podcast feed to extract episode info with rich metadata."""
    # print(f"Fetching feed from {FEED_URL}...")
    try:
        response = requests.get(FEED_URL)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"Error fetching feed: {e}")
        return []

    # The feed is XML, so we use the xml parser for reliability.
    soup = BeautifulSoup(response.content, "xml")
    episodes = []

    # In an RSS feed, episodes are inside <item> tags
    for item in soup.find_all("item"):
        episode_data = {}

        # Title
        title_tag = item.find("title")
        if title_tag:
            episode_data["title"] = title_tag.get_text(strip=True)
        else:
            continue  # Skip episodes without titles

        # Date
        date_tag = item.find("pubDate")
        if date_tag:
            # Format: Tue, 08 Jul 2025 07:00:00 GMT
            date_str = date_tag.get_text(strip=True)
            try:
                # We split and take all but the last part to remove the timezone
                date_str_no_tz = " ".join(date_str.split()[:-1])
                date_obj = datetime.strptime(date_str_no_tz, "%a, %d %b %Y %H:%M:%S")
                episode_data["date"] = date_obj
            except (ValueError, IndexError) as e:
                print(f"Could not parse date: {date_str}, error: {e}")
                continue

        # MP3 URL
        enclosure_tag = item.find("enclosure", type="audio/mpeg")
        if enclosure_tag and enclosure_tag.has_attr("url"):
            episode_data["audio_url"] = enclosure_tag["url"]
        else:
            continue  # Skip episodes without audio

        # Episode link (the web page for this episode)
        link_tag = item.find("link")
        if link_tag:
            episode_data["link"] = link_tag.get_text(strip=True)

        # Description
        description_tag = item.find("description")
        if description_tag:
            episode_data["description"] = description_tag.get_text(strip=True)

        # iTunes-specific metadata
        itunes_duration_tag = item.find("itunes:duration")
        if itunes_duration_tag:
            episode_data["duration"] = itunes_duration_tag.get_text(strip=True)

        itunes_episode_tag = item.find("itunes:episode")
        if itunes_episode_tag:
            episode_data["episode_number"] = itunes_episode_tag.get_text(strip=True)

        itunes_subtitle_tag = item.find("itunes:subtitle")
        if itunes_subtitle_tag:
            episode_data["subtitle"] = itunes_subtitle_tag.get_text(strip=True)

        # GUID (unique identifier)
        guid_tag = item.find("guid")
        if guid_tag:
            episode_data["guid"] = guid_tag.get_text(strip=True)

        # Only add episodes that have the minimum required fields
        if (
            "title" in episode_data
            and "date" in episode_data
            and "audio_url" in episode_data
        ):
            episodes.append(episode_data)

    return episodes


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


def ensure_guid(episode_data: Dict) -> str:
    """
    Generate reliable GUID with fallback for database uniqueness.

    Args:
        episode_data: Dictionary with episode information from RSS

    Returns:
        str: GUID for the episode (from RSS or generated)
    """
    # Primary: Use RSS guid if available
    if episode_data.get("guid"):
        guid = str(episode_data["guid"]).strip()
        if guid:
            return guid

    # Fallback: Generate deterministic GUID from title + date
    title = episode_data.get("title", "unknown")
    date_obj = episode_data.get("date")

    if date_obj:
        date_str = date_obj.isoformat()
    else:
        date_str = datetime.now().isoformat()

    # Create deterministic content string
    content = f"{title}|{date_str}"

    # Generate short hash (12 chars should be collision-resistant for podcast episodes)
    hash_value = hashlib.md5(content.encode("utf-8")).hexdigest()[:12]

    return f"generated-{hash_value}"


def filter_recent_episodes(episodes: List[Dict], days_back: int) -> List[Dict]:
    """
    Filter episodes to recent timeframe.

    Args:
        episodes: List of episode dictionaries from RSS
        days_back: Number of days back to include (0 for all episodes)

    Returns:
        List of filtered episodes
    """
    if days_back <= 0:  # full_sync case
        return episodes

    cutoff_date = datetime.now() - timedelta(days=days_back)

    filtered = []
    for episode in episodes:
        episode_date = episode.get("date")
        if episode_date and episode_date >= cutoff_date:
            filtered.append(episode)

    return filtered


def clean_html_description(html_content: str) -> str:
    """
    Clean HTML from episode description to make it human readable.

    Removes all HTML tags and converts HTML entities to plain text.
    No special formatting preservation - just clean, readable text.

    Args:
        html_content: Raw HTML content from RSS description

    Returns:
        str: Clean plain text description
    """
    if not html_content:
        return html_content

    try:
        # Parse HTML content
        soup = BeautifulSoup(html_content, "html.parser")

        # Get clean text (automatically handles HTML entities)
        clean_text = soup.get_text()

        # Clean up whitespace
        # Replace multiple whitespace chars with single space
        clean_text = re.sub(r"\s+", " ", clean_text)

        # Remove leading/trailing whitespace
        clean_text = clean_text.strip()

        return clean_text

    except Exception as e:
        # If HTML cleaning fails, log error and return original content
        logger = logging.getLogger("sync_episodes")
        logger.error(f"Failed to clean HTML from description: {e}")
        return html_content


def episode_exists_in_db(session, guid: str) -> bool:
    """
    Check if episode already exists in database.

    Args:
        session: Database session
        guid: Episode GUID to check

    Returns:
        bool: True if episode exists, False otherwise
    """
    return session.query(Episode).filter_by(guid=guid).first() is not None


def create_episode_record(session, episode_data: Dict, guid: str) -> Episode:
    """
    Create new episode record in database.

    Args:
        session: Database session
        episode_data: Episode information from RSS
        guid: Generated/validated GUID

    Returns:
        Episode: Created episode record
    """
    # Clean HTML from description before storing
    raw_description = episode_data.get("description")
    clean_description = (
        clean_html_description(raw_description) if raw_description else None
    )

    episode = Episode(
        guid=guid,
        title=episode_data.get("title", "Unknown Title"),
        description=clean_description,
        published_date=episode_data.get("date", datetime.now()),
        audio_url=episode_data.get("audio_url", ""),
    )

    session.add(episode)
    return episode


def sync_episodes(
    full_sync: bool = False,
    days_back: int = 30,
    limit: Optional[int] = None,
    dry_run: bool = False,
) -> Dict[str, int]:
    """
    Main sync function - fetches RSS episodes and syncs to database.

    Args:
        full_sync: If True, sync all episodes (ignores days_back)
        days_back: Days back to sync (default: 30)
        limit: Maximum episodes to process (for testing)
        dry_run: If True, show what would be synced without saving

    Returns:
        Dict with sync statistics
    """
    logger = logging.getLogger("sync_episodes")

    print("Fetching episodes from RSS feed...")
    logger.info("Starting episode sync")

    try:
        # Fetch all episodes from RSS
        all_episodes = fetch_podcast_episodes()

        if not all_episodes:
            print("No episodes found in RSS feed")
            logger.warning("No episodes found in RSS feed")
            return {"processed": 0, "added": 0, "skipped": 0, "errors": 0}

        print(f"Found {len(all_episodes)} episodes in feed")
        logger.info(f"Found {len(all_episodes)} episodes in RSS feed")

        # Filter by date range
        if full_sync:
            episodes_to_process = all_episodes
            print("Processing all episodes (full sync)")
        else:
            episodes_to_process = filter_recent_episodes(all_episodes, days_back)
            print(f"Filtering to episodes from last {days_back} days...")
            print(f"Found {len(episodes_to_process)} recent episodes")

        if not episodes_to_process:
            print("No episodes to process")
            return {"processed": 0, "added": 0, "skipped": 0, "errors": 0}

        # Sort episodes by publication date (oldest first) for chronological ID assignment
        episodes_to_process.sort(key=lambda ep: ep["date"])
        print("Episodes sorted by publication date (oldest first)")

        # Apply limit AFTER sorting so we get the oldest episodes when limiting
        if limit:
            episodes_to_process = episodes_to_process[:limit]
            print(f"Limited to first {limit} episodes after sorting (oldest first)")

        print(f"Processing {len(episodes_to_process)} episodes...")
        if dry_run:
            print("DRY RUN - showing episodes that would be added:")

        logger.info(
            f"Processing {len(episodes_to_process)} episodes (dry_run={dry_run})"
        )

        # Initialize stats
        stats = {"processed": 0, "added": 0, "skipped": 0, "errors": 0}

        # Process episodes with database session
        with get_db_session() as session:
            for episode_data in episodes_to_process:
                try:
                    # Generate GUID with fallback
                    guid = ensure_guid(episode_data)

                    # Check if episode already exists
                    if episode_exists_in_db(session, guid):
                        # Only show skipped episodes in verbose mode or dry-run
                        if dry_run:
                            pass  # Don't show skipped in dry-run (only show what would be added)
                        else:
                            print(
                                f'- Skipped: "{episode_data.get("title", "Unknown")}" (already exists)'
                            )
                        stats["skipped"] += 1
                    else:
                        # Episode would be added
                        title = episode_data.get("title", "Unknown Title")
                        date_str = episode_data.get("date", datetime.now()).strftime(
                            "%Y-%m-%d"
                        )

                        if dry_run:
                            print(f'✓ Would add: "{title}" ({date_str})')
                        else:
                            create_episode_record(session, episode_data, guid)
                            session.commit()
                            print(f'✓ Added: "{title}" ({date_str})')

                        stats["added"] += 1

                    stats["processed"] += 1

                except Exception as e:
                    title = episode_data.get("title", "Unknown")
                    print(f'✗ Error processing "{title}": {e}')
                    logger.error(f"Error processing episode '{title}': {e}")
                    stats["errors"] += 1
                    # Continue processing other episodes
                    continue

        return stats

    except Exception as e:
        print(f"✗ Sync failed: {e}")
        logger.error(f"Sync failed: {e}")
        raise


def print_summary(stats: Dict[str, int], dry_run: bool = False):
    """Print sync summary statistics."""
    print()
    action = "Would be synced" if dry_run else "Sync completed"
    print(
        f"{action}: {stats['processed']} processed, {stats['added']} added, {stats['skipped']} skipped, {stats['errors']} errors"
    )

    if stats["errors"] > 0:
        print("Check logs/sync_episodes.log for detailed error information")


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Sync podcast episodes from RSS feed to database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python src/scripts/sync_episodes.py                    # Sync last 30 days
  python src/scripts/sync_episodes.py --full-sync        # Sync all episodes  
  python src/scripts/sync_episodes.py --days 60          # Sync last 60 days
  python src/scripts/sync_episodes.py --limit 5 --dry-run # Test mode
        """,
    )

    parser.add_argument(
        "--full-sync", action="store_true", help="Sync all episodes (ignores --days)"
    )
    parser.add_argument(
        "--days", type=int, default=30, help="Days back to sync (default: 30)"
    )
    parser.add_argument(
        "--limit", type=int, help="Max episodes to process (for testing)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be synced without saving",
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Detailed console output"
    )

    return parser.parse_args()


def main():
    """Main entry point."""
    args = parse_arguments()

    # Setup logging
    logger = setup_logging(verbose=args.verbose)

    try:
        # Run sync
        stats = sync_episodes(
            full_sync=args.full_sync,
            days_back=args.days,
            limit=args.limit,
            dry_run=args.dry_run,
        )

        # Print summary
        print_summary(stats, dry_run=args.dry_run)

        # Log completion
        logger.info(f"Sync completed: {stats}")

        # Exit with appropriate code
        sys.exit(0 if stats["errors"] == 0 else 1)

    except KeyboardInterrupt:
        print("\nSync interrupted by user")
        logger.info("Sync interrupted by user")
        sys.exit(130)

    except Exception as e:
        print(f"✗ Sync failed: {e}")
        logger.error(f"Sync failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
