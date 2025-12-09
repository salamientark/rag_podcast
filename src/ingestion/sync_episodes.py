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
import os
import sys
from typing import Optional
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv

import requests
from bs4 import BeautifulSoup

from src.db import get_db_session, Episode
from src.db.models import ProcessingStage
from src.logger import setup_logging, log_function


# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Init logger
logger = setup_logging(logger_name="sync_episodes", log_file="logs/sync_episodes.log")


# ============ RECONCILIATION FUNCTIONS ============
@log_function(logger_name="sync_episodes", log_execution_time=True)
def find_episode_file(episode_id: int, file_dir: Path, pattern: str) -> Optional[Path]:
    """
    Find episode file using glob pattern used to find audio and transcript file.
    Returns Path if found and valid, None otherwise.
    """
    matches = list(file_dir.glob(pattern))

    # Edge case
    if len(matches) == 0:
        return None
    if len(matches) > 1:
        logger.warning(f"Multiple files found for episode {episode_id}: {matches}")
        return None

    file_path = matches[0]

    # Validate file size (>0 bytes)
    if file_path.stat().st_size == 0:
        logger.warning(f"File for episode {episode_id} is empty, skipping")
        return None
    return file_path


def determine_stage_for_file(
    audio_exists: bool,
    raw_exists: bool,
    formatted_exists: bool
) -> ProcessingStage:
    """
    Determine highest processing stage based on which files exist.
    
    Returns the maximum stage that can be proven by existing files.
    """
    if formatted_exists and raw_exists and audio_exists:
        return ProcessingStage.FORMATTED_TRANSCRIPT
    elif raw_exists and audio_exists:
        return ProcessingStage.RAW_TRANSCRIPT
    elif audio_exists:
        return ProcessingStage.AUDIO_DOWNLOADED
    else:
        return ProcessingStage.SYNCED
    

@log_function(logger_name="sync_episodes", log_execution_time=True)
def reconcile_episode_status(
    episodes,
    audio_dir: Path = Path("data/audio"),
    transcript_dir: Path = Path("data/transcript"),
    dry_run: bool = False,
) -> dict:
    """
    Reconcile episode processing stages based on filesystem state.
    
    Args:
        episodes: List of Episode objects to reconcile
        audio_dir: Directory containing audio files
        transcript_dir: Directory containing transcript files
        dry_run: If True, do not commit changes to database
        
    Returns:
        Dict with stats: {"processed": N, "updated": N, "unchanged": N, "errors": N}
    """
    logger = logging.getLogger("sync_episodes")
    
    if not episodes:
        print("No episodes to reconcile")
        return {"processed": 0, "updated": 0, "unchanged": 0, "errors": 0}
    
    print(f"Reconciling {len(episodes)} episodes from filesystem...")
    
    stats = {"processed": 0, "updated": 0, "unchanged": 0, "errors": 0}
    
    with get_db_session() as session:
        for episode in episodes:
            try:
                # Refresh episode to ensure it's attached to this session
                episode = session.merge(episode)
                
                # Find files using patterns
                episode_transcript_dir = f"{transcript_dir}/episode_{episode.id:03d}"

                audio_pattern = f"episode_{episode.id:03d}_*.mp3"
                audio_path = find_episode_file(episode.id, Path(audio_dir), audio_pattern)
                
                raw_pattern = f"raw_episode_{episode.id}_*.json"
                raw_path = find_episode_file(episode.id, Path(episode_transcript_dir), raw_pattern)
                
                formatted_pattern = f"formatted_episode_{episode.id}_*.txt"
                formatted_path = find_episode_file(episode.id, Path(episode_transcript_dir), formatted_pattern)
                
                # Determine target stage
                target_stage = determine_stage_for_file(
                    audio_exists=audio_path is not None,
                    raw_exists=raw_path is not None,
                    formatted_exists=formatted_path is not None
                )
                
                # Get stage ordering for comparison
                stage_order = list(ProcessingStage)
                current_stage_index = stage_order.index(episode.processing_stage)
                target_stage_index = stage_order.index(target_stage)
                
                # Only update if moving forward
                if target_stage_index > current_stage_index:
                    # Update stage
                    old_stage = episode.processing_stage
                    episode.processing_stage = target_stage
                    
                    # Update paths with warnings for overwrites
                    if audio_path:
                        if episode.audio_file_path and episode.audio_file_path != str(audio_path):
                            logger.warning(
                                f"Episode {episode.id}: Overwriting audio_file_path "
                                f"from '{episode.audio_file_path}' to '{audio_path}'"
                            )
                        episode.audio_file_path = str(audio_path)
                    
                    if raw_path:
                        if episode.raw_transcript_path and episode.raw_transcript_path != str(raw_path):
                            logger.warning(
                                f"Episode {episode.id}: Overwriting raw_transcript_path "
                                f"from '{episode.raw_transcript_path}' to '{raw_path}'"
                            )
                        episode.raw_transcript_path = str(raw_path)
                    
                    if formatted_path:
                        if episode.formatted_transcript_path and episode.formatted_transcript_path != str(formatted_path):
                            logger.warning(
                                f"Episode {episode.id}: Overwriting formatted_transcript_path "
                                f"from '{episode.formatted_transcript_path}' to '{formatted_path}'"
                            )
                        episode.formatted_transcript_path = str(formatted_path)

                    # Commit changes
                    if not dry_run:
                        session.commit()
                    
                    print(f"  ✓ Episode {episode.id}: {old_stage.value} → {target_stage.value}")
                    logger.info(f"Updated episode {episode.id} from {old_stage.value} to {target_stage.value}")
                    stats["updated"] += 1
                else:
                    print(f"  - Episode {episode.id}: No update needed (stage: {episode.processing_stage.value})")
                    stats["unchanged"] += 1
                
                stats["processed"] += 1
                
            except Exception as e:
                print(f"  ✗ Error reconciling episode {episode.id}: {e}")
                logger.error(f"Error reconciling episode {episode.id}: {e}")
                stats["errors"] += 1
    
    return stats


# ============ RSS SYNC FUNCTIONS ============
@log_function(logger_name="sync_episodes", log_execution_time=True)
def fetch_podcast_episodes():
    """Fetch episodes from RSS feed - proven working approach"""
    # Get feed URL from .env
    env = load_dotenv()
    if not env:
        raise EnvironmentError("Could not load .env file")
    FEED_URL = os.getenv("FEED_URL")

    logger.info(f"Fetching feed from {FEED_URL}...")
    try:
        response = requests.get(FEED_URL, timeout=30)
        response.raise_for_status()
    except requests.RequestException as e:
        logger.error(f"Error fetching feed: {e}")
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


@log_function(logger_name="sync_episodes", log_execution_time=True)
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
                        processing_stage="synced",
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

# ============ SHARED ENTRY POINT ============
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
        "--reconcile",
        action="store_true",
        help="Reconcile db entries from filesystem state",
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Detailed console output"
    )

    args = parser.parse_args()

    # Setup logging using centralized utility
    logger = setup_logging(
        logger_name="sync_episodes",
        log_file="logs/sync_episodes.log",
        verbose=args.verbose,
    )
    logger.info("Starting episode sync")

    try:
        # Validate reconcile usage
        if args.reconcile and not (args.full_sync or args.limit):
            parser.error("--reconcile requires either --full-sync or --limit")
        
        if args.reconcile:
            # RECONCILIATION WORKFLOW: Query database and reconcile from filesystem
            print("Running reconciliation from filesystem...")
            
            with get_db_session() as session:
                query = session.query(Episode).order_by(Episode.published_date.desc())
                
                # Apply filtering
                if not args.full_sync and args.days > 0:
                    cutoff_date = datetime.now() - timedelta(days=args.days)
                    query = query.filter(Episode.published_date >= cutoff_date)
                    print(f"Filtering to episodes from last {args.days} days")
                
                if args.limit:
                    query = query.limit(args.limit)
                    print(f"Limited to {args.limit} episodes")
                
                episodes = query.all()
            
            # Run reconciliation
            stats = reconcile_episode_status(episodes, dry_run=args.dry_run)
            
            # Print summary
            print(
                f"\nReconciliation completed: {stats['processed']} processed, "
                f"{stats['updated']} updated, {stats['unchanged']} unchanged, "
                f"{stats['errors']} errors"
            )
        else:
            # EXISTING RSS SYNC WORKFLOW
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
                f"\nCompleted: {stats['processed']} processed, {stats['added']} added, "
                f"{stats['skipped']} skipped, {stats['errors']} errors"
            )
        if stats["errors"] > 0:
            print("Check logs/sync_episodes.log for detailed error information")
        logger.info(f"Operation completed: {stats}")
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
