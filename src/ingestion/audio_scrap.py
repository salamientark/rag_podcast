#!/usr/bin/env python3
"""
Audio Scraper for Podcast Episodes - Optimized Version

Downloads audio files using browser headers to handle feedpress.me redirects.
Based on successful testing with simple approach.

Usage:
    uv run -m src.ingestion.audio_scrap                    # Download all missing episodes
    uv run -m src.ingestion.audio_scrap --limit 5          # Download 5 most recent missing
    uv run -m src.ingestion.audio_scrap --dry-run          # Test mode (fast)
"""

import argparse
import logging
import os
import re
import sys
import time
from pathlib import Path

import requests

from src.db import get_db_session, Episode, ProcessingStage
from src.logger import setup_logging, log_function


# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


def sanitize_filename(title, max_length=100):
    """
    Clean filename for safe filesystem usage - removes ALL punctuation.

    Strategy for short, efficient filenames:
    - Remove all punctuation and special characters
    - Convert to lowercase for consistency
    - Limit to max_length characters (default 100)
    - Truncate at word boundaries to avoid cutting words

    Args:
        title: Episode title to sanitize
        max_length: Maximum length for filename (default 100)

    Returns:
        Sanitized filename string
    """
    if not title:
        return "unknown_episode"

    # Convert to lowercase for consistency
    safe = title.lower()

    # Remove ALL punctuation and special characters, keep only alphanumeric and spaces
    safe = re.sub(r"[^a-z0-9\s]", "", safe)

    # Replace multiple spaces with single underscore
    safe = re.sub(r"\s+", "_", safe)

    # Remove leading/trailing underscores
    safe = safe.strip("_")

    # Truncate if too long, breaking at word boundary
    if len(safe) > max_length:
        safe = safe[:max_length].rsplit("_", 1)[0]

    return safe if safe else "unknown_episode"


def generate_filename(episode_number: int, title: str):
    """Generate filename: episode_{number:03d}_{title}.mp3"""
    safe_title = sanitize_filename(title)
    return f"episode_{episode_number:03d}_{safe_title}.mp3"


@log_function(logger_name="audio_scraper", log_execution_time=True)
def update_episode_status(uuid: str, audio_file_path: str) -> bool:
    """
    Update episode database record after successful audio download.

    Args:
        uuid: Episode UUID in the database
        audio_file_path: Path to the downloaded audio file

    Returns:
        bool: True if update successful, False otherwise
    """
    logger = logging.getLogger("audio_scraper")
    try:
        with get_db_session() as session:
            episode = session.query(Episode).filter_by(uuid=uuid).first()

            if not episode:
                logger.error(f"Episode UUID {uuid} not found in database")
                return False

            # Update db fields
            stage_order = list(ProcessingStage)
            current_stage_index = stage_order.index(episode.processing_stage)
            target_stage_index = stage_order.index(ProcessingStage.AUDIO_DOWNLOADED)
            if current_stage_index < target_stage_index:
                episode.processing_stage = ProcessingStage.AUDIO_DOWNLOADED
            episode.audio_file_path = audio_file_path

            session.commit()
            logger.info(f"Updated episode UUID {uuid} with audio file path")
            return True
    except Exception as e:
        logger.error(f"Failed to update episode UUID {uuid}: {e}")
        return False


@log_function(logger_name="audio_scraper", log_execution_time=True)
def get_episodes_from_db(limit=None):
    """Get episodes from database, ordered by most recent first, using database ID as episode number"""
    logger = logging.getLogger("audio_scraper")

    try:
        with get_db_session() as session:
            query = session.query(Episode).order_by(Episode.published_date.desc())
            if limit:
                query = query.limit(limit)

            episodes = query.all()

            episode_list = []
            for ep in episodes:
                if ep.audio_url is not None and str(ep.audio_url).strip():
                    # Use database ID as episode number for filenames
                    episode_list.append(
                        {
                            "uuid": ep.uuid,
                            "podcast": ep.podcast,
                            "title": ep.title,
                            "audio_url": ep.audio_url,
                            "published_date": ep.published_date,
                            "episode_id": ep.episode_id,  # Use database ID as episode number
                        }
                    )

            logger.info(f"Retrieved {len(episode_list)} episodes from database")
            return episode_list

    except Exception as e:
        logger.error(f"Failed to query database: {e}")
        raise


def get_existing_files(audio_dir):
    """Get set of existing MP3 files"""
    audio_path = Path(audio_dir)
    if not audio_path.exists():
        return set()

    return {
        f.name
        for f in audio_path.iterdir()
        if f.is_file() and f.suffix.lower() == ".mp3"
    }


@log_function(logger_name="audio_scraper", log_execution_time=True)
def download_episode(
    episode_number, title, url, workspace, max_retries=3
) -> tuple[bool, str]:
    """Download single episode with browser headers for feedpress.me URLs"""
    logger = logging.getLogger("audio_scraper")

    os.makedirs(workspace, exist_ok=True)
    filename = generate_filename(episode_number, title)
    filepath = os.path.join(workspace, filename)

    # Check if already exists
    if os.path.exists(filepath):
        logger.info(f"Audio for '{title[:40]}...' already downloaded")
        return True, filepath

    # Browser headers to handle feedpress.me redirects properly
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Accept": "audio/mpeg, audio/*, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
    }

    for attempt in range(max_retries):
        try:
            logger.info(f"Downloading {filename} (attempt {attempt + 1}/{max_retries})")
            print(f"  Downloading: {title[:50]}...")

            # Download with browser headers and redirects
            response = requests.get(url, stream=True, headers=headers, timeout=120)
            response.raise_for_status()

            # Write file in chunks
            with open(filepath, "wb") as f:
                downloaded = 0
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)

            # Verify file size
            file_size = os.path.getsize(filepath)
            if file_size < 100 * 1024:  # Less than 100KB is suspicious
                logger.warning(
                    f"File {filename} is suspiciously small: {file_size} bytes"
                )
                os.remove(filepath)
                raise Exception(f"Downloaded file too small: {file_size} bytes")

            logger.info(f"Successfully downloaded {filename} ({file_size:,} bytes)")
            print(f"  ✓ Downloaded {filename} ({file_size:,} bytes)")
            return True, filepath

        except requests.exceptions.RequestException as e:
            logger.warning(f"Download attempt {attempt + 1} failed for {filename}: {e}")
            print(f"  ✗ Attempt {attempt + 1} failed: {e}")

            # Clean up partial file
            if os.path.exists(filepath):
                os.remove(filepath)

        except Exception as e:
            logger.error(f"Unexpected error downloading {filename}: {e}")
            print(f"  ✗ Unexpected error: {e}")

            # Clean up partial file
            if os.path.exists(filepath):
                os.remove(filepath)

        # Wait before retry
        if attempt < max_retries - 1:
            wait_time = 2**attempt  # 1s, 2s, 4s
            logger.info(f"Waiting {wait_time}s before retry...")
            time.sleep(wait_time)

    logger.error(f"Failed to download {filename} after {max_retries} attempts")
    print(f"  ✗ Failed after {max_retries} attempts")
    return False, ""


@log_function(logger_name="audio_scraper", log_execution_time=True)
def download_missing_episodes(audio_dir="data/audio", limit=None, dry_run=False):
    """Main download function"""
    logger = logging.getLogger("audio_scraper")

    print(f"Checking for missing episodes in {audio_dir}...")
    logger.info("Starting audio download process")

    try:
        # Get episodes from database
        print("Querying database for episodes...")
        all_episodes = get_episodes_from_db(limit=limit)

        if not all_episodes:
            print("No episodes found in database")
            return {"total": 0, "downloaded": 0, "failed": 0, "skipped": 0}

        print(f"Found {len(all_episodes)} episodes in database")

        # Get existing files
        print("Scanning for existing files...")
        existing_files = get_existing_files(audio_dir)
        print(f"Found {len(existing_files)} existing audio files")

        # Find missing episodes
        missing_episodes = []
        for episode in all_episodes:
            expected_filename = generate_filename(
                episode["episode_id"], episode["title"]
            )
            if expected_filename not in existing_files:
                missing_episodes.append(episode)

        print(f"Found {len(missing_episodes)} episodes that need downloading")

        if not missing_episodes:
            print("All episodes already downloaded!")
            return {
                "total": len(all_episodes),
                "downloaded": 0,
                "failed": 0,
                "skipped": len(existing_files),
            }

        # Apply limit to missing episodes
        if limit and limit > 0:
            missing_episodes = missing_episodes[:limit]
            print(f"Limited to {limit} most recent missing episodes")

        if dry_run:
            print("DRY RUN - Episodes that would be downloaded:")
            for ep in missing_episodes:
                filename = generate_filename(ep["episode_id"], ep["title"])
                print(f"  ✓ Would download: {filename}")
            return {
                "total": len(all_episodes),
                "downloaded": 0,
                "failed": 0,
                "skipped": len(existing_files),
            }

        # Download missing episodes
        print(f"\nDownloading {len(missing_episodes)} missing episodes...")
        logger.info(f"Starting download of {len(missing_episodes)} episodes")

        stats = {
            "total": len(all_episodes),
            "downloaded": 0,
            "failed": 0,
            "skipped": len(existing_files),
            "db_updated": 0,
            "db_failed": 0,
        }

        for i, episode in enumerate(missing_episodes, 1):
            print(f"\n[{i}/{len(missing_episodes)}] {episode['title'][:60]}...")

            success, filepath = download_episode(
                episode["episode_id"],
                episode["title"],
                episode["audio_url"],
                audio_dir,
            )

            if success:
                stats["downloaded"] += 1
                if update_episode_status(episode["uuid"], filepath):
                    stats["db_updated"] += 1
                else:
                    logger.warning(
                        f"Downloaded episode {episode['uuid']} but failed to update database"
                    )
                    stats["db_failed"] += 1
            else:
                stats["failed"] += 1

        return stats

    except Exception as e:
        print(f"✗ Download process failed: {e}")
        logger.error(f"Download process failed: {e}")
        raise


def main():
    """Main CLI function"""
    parser = argparse.ArgumentParser(
        description="Download missing podcast episode audio files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  uv run -m src.ingestion.audio_scrap                    # Download all missing episodes
  uv run -m src.ingestion.audio_scrap --limit 5          # Download 5 most recent missing
  uv run -m src.ingestion.audio_scrap --dry-run          # Test mode (show what would download)
  uv run -m src.ingestion.audio_scrap --verbose          # Verbose output with detailed logs
        """,
    )

    parser.add_argument(
        "--audio-dir", default="data/audio", help="Directory to save audio files"
    )
    parser.add_argument(
        "--limit", type=int, help="Maximum episodes to download (most recent missing)"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would be downloaded"
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Detailed console output"
    )

    args = parser.parse_args()

    # Setup logging using centralized utility
    logger = setup_logging(
        logger_name="audio_scraper",
        log_file="logs/audio_download.log",
        verbose=args.verbose,
    )

    try:
        # Run download process
        stats = download_missing_episodes(
            audio_dir=args.audio_dir, limit=args.limit, dry_run=args.dry_run
        )

        # Print summary
        print(f"\n{'=' * 60}")
        action = "Would be processed" if args.dry_run else "Download completed"
        print(f"{action}:")
        print(f"  Total episodes: {stats['total']}")
        print(f"  Downloaded: {stats['downloaded']}")
        print(f"  Already existed: {stats['skipped']}")
        print(f"  Failed: {stats['failed']}")
        print(f"  DB updated: {stats.get('db_updated', 0)}")
        print(f"  DB update failed: {stats.get('db_failed', 0)}")

        if stats["failed"] > 0:
            print("\n⚠️  Check logs/audio_download.log for detailed error information")

        logger.info(f"Download process completed: {stats}")

        # Exit with appropriate code
        sys.exit(0 if stats["failed"] == 0 else 1)

    except KeyboardInterrupt:
        print("\nDownload interrupted by user")
        logger.info("Download interrupted by user")
        sys.exit(130)

    except Exception as e:
        print(f"✗ Download process failed: {e}")
        logger.error(f"Download process failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
