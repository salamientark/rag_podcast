#!/usr/bin/env python3
"""
Script to reprocess failed episodes (ProcessingStage.ERROR).
"""

import csv
from datetime import datetime
import sys
import argparse
import asyncio
from collections import defaultdict
from typing import List, Dict, Any, Optional, Set, Tuple

# Add project root to sys.path if running from scripts directory
import os
from sqlalchemy import tuple_

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.logger import setup_logging
from src.db.database import get_db_session
from src.db.models import Episode, ProcessingStage, Podcast
from src.pipeline.orchestrator import run_pipeline


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Reprocess failed episodes")
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Limit number of episodes to process (default: 5)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Process all failed episodes (overrides --limit)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be processed without executing",
    )
    return parser.parse_args()


def get_recitation_failures(
    filename: str = "reprocess_errors.csv",
) -> Set[Tuple[str, int]]:
    """
    Read previous errors and identify episodes that failed due to RECITATION.
    Returns a set of (podcast_name, episode_id) tuples.
    """
    exclusions = set()
    if not os.path.isfile(filename):
        return exclusions

    try:
        with open(filename, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("finish_reason") == "RECITATION":
                    try:
                        p_name = row["podcast_name"]
                        e_id = int(row["episode_id"])
                        exclusions.add((p_name, e_id))
                    except (ValueError, KeyError):
                        continue
    except Exception as e:
        print(
            f"Warning: Failed to read exclusion list from {filename}: {e}",
            file=sys.stderr,
        )

    return exclusions


def get_failed_episodes(
    limit: Optional[int] = None, exclude_episodes: Optional[Set[Tuple[str, int]]] = None
) -> List[Dict[str, Any]]:
    """
    Get failed episodes from database.
    Returns list of dicts with necessary info to avoid detachment issues.
    """
    with get_db_session() as session:
        query = session.query(Episode).filter(
            Episode.processing_stage == ProcessingStage.ERROR
        )

        # Apply exclusions directly in the query
        if exclude_episodes:
            # 1. Fetch all podcasts to map name -> ID
            podcasts = session.query(Podcast.id, Podcast.name).all()
            podcast_map = {name: pid for pid, name in podcasts}

            # 2. Build list of (podcast_id, episode_id) tuples to exclude
            excluded_db_tuples = []
            for p_name, e_id in exclude_episodes:
                if p_name in podcast_map:
                    excluded_db_tuples.append((podcast_map[p_name], e_id))

            # 3. Apply NOT IN filter if we have valid IDs
            if excluded_db_tuples:
                query = query.filter(
                    tuple_(Episode.podcast_id, Episode.episode_id).notin_(
                        excluded_db_tuples
                    )
                )

        # Order by most recent failures (published_date desc)
        query = query.order_by(Episode.published_date.desc())

        if limit is not None:
            query = query.limit(limit)

        episodes = query.all()

        # Extract data while session is open
        result = []
        for ep in episodes:
            # Access podcast_rel to trigger loading
            podcast = ep.podcast_rel
            if podcast:
                result.append(
                    {
                        "episode_id": ep.episode_id,
                        "podcast_id": ep.podcast_id,
                        "podcast_name": podcast.name,
                        "feed_url": podcast.feed_url,
                        "title": ep.title,
                    }
                )
            else:
                # Fallback if relationship not loaded or missing (shouldn't happen with FK)
                print(
                    f"Warning: Episode {ep.uuid} has no associated podcast",
                    file=sys.stderr,
                )

        return result


def save_error(
    failures: List[Dict[str, Any]], filename: str = "reprocess_errors.csv"
) -> None:
    """
    Save failed episodes to a CSV file.

    Args:
        failures: List of dicts with error details
        filename: Output CSV filename
    """
    if not failures:
        return

    fieldnames = [
        "podcast_name",
        "episode_name",
        "episode_id",
        "finish_reason",
        "notes",
        "timestamp",
    ]

    # In overwrite mode (as requested), we always write a new header if we are starting fresh
    # But since we might call this multiple times in a loop (per podcast), we should probably append
    # if we want to capture all errors from one run of the script.
    # However, the user said "Overwrite". If I overwrite every time I call save_error inside the loop,
    # I will lose previous iterations.
    # The loop in main() iterates over podcasts. If I overwrite in each iteration, I only keep the last podcast's errors.
    # So I should probably accumulate errors in main() and save once at the end, OR append.
    # Given "Overwrite", I assume they mean "Overwrite the file from previous runs of the script".
    # So I should write 'w' mode once at start, or accumulate all errors and write once.

    # Let's accumulate in main and write once.

    try:
        file_exists = os.path.isfile(filename)
        with open(filename, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if not file_exists:
                writer.writeheader()

            timestamp = datetime.now().isoformat()
            for error in failures:
                row = {
                    "podcast_name": error.get("podcast_name", ""),
                    "episode_name": error.get("episode_name", ""),
                    "episode_id": error.get("episode_id", ""),
                    "finish_reason": error.get("finish_reason", "unknown"),
                    "notes": error.get("notes", ""),
                    "timestamp": timestamp,
                }
                writer.writerow(row)
        print(f"Errors saved to {filename}")
    except Exception as e:
        print(f"Failed to save errors to CSV: {e}", file=sys.stderr)


async def main():
    """Main entry point."""
    args = parse_arguments()

    # Setup logging
    logger = setup_logging(
        logger_name="reprocess_failed",
        log_file="logs/reprocess_failed.log",
        verbose=True,
    )

    logger.info("=== REPROCESS FAILED EPISODES STARTED ===")

    # Get exclusion list
    exclusions = get_recitation_failures()
    if exclusions:
        logger.info(
            f"Found {len(exclusions)} episodes to skip from previous RECITATION errors."
        )

    if args.dry_run:
        logger.info("DRY RUN MODE ENABLED")
        print("DRY RUN MODE ENABLED - No changes will be made")

    limit = None if args.all else args.limit
    logger.info(f"Mode: {'ALL' if args.all else f'Limit {limit}'}")

    try:
        failed_episodes = get_failed_episodes(limit, exclude_episodes=exclusions)
    except Exception as e:
        logger.error(f"Error fetching failed episodes: {e}")
        print(f"Error fetching failed episodes: {e}", file=sys.stderr)
        sys.exit(1)

    if not failed_episodes:
        logger.info("No failed episodes found.")
        print("No failed episodes found.")
        return

    logger.info(f"Found {len(failed_episodes)} failed episodes.")
    print(f"Found {len(failed_episodes)} failed episodes.")

    # Group by podcast
    episodes_by_podcast = defaultdict(list)
    podcasts_info = {}

    for ep in failed_episodes:
        p_id = ep["podcast_id"]
        episodes_by_podcast[p_id].append(ep["episode_id"])
        if p_id not in podcasts_info:
            podcasts_info[p_id] = {
                "name": ep["podcast_name"],
                "feed_url": ep["feed_url"],
            }

    # Process each podcast group
    failed_to_process = []
    all_pipeline_failures = []

    for p_id, ep_ids in episodes_by_podcast.items():
        p_info = podcasts_info[p_id]

        logger.info(
            f"Processing {len(ep_ids)} episodes for podcast '{p_info['name']}' (ID: {p_id})"
        )
        logger.info(f"Episode IDs: {ep_ids}")

        if args.dry_run:
            continue

        try:
            failures = await run_pipeline(
                episodes_id=ep_ids,
                podcast_id=p_id,
                podcast_name=p_info["name"],
                feed_url=p_info["feed_url"],
                use_cloud_storage=True,
                force=True,  # Must force to reprocess ERROR stage
                verbose=True,
            )
            if failures:
                all_pipeline_failures.extend(failures)

        except Exception as e:
            failed_to_process.append((p_info["name"], str(e)))
            logger.error(
                f"Failed to reprocess podcast {p_info['name']}: {e}", exc_info=True
            )
            print(f"Failed to reprocess podcast {p_info['name']}: {e}", file=sys.stderr)

    # Save errors if any
    if all_pipeline_failures:
        save_error(all_pipeline_failures)

    logger.info("=== REPROCESS COMPLETED ===")
    if failed_to_process:
        logger.warning("Some podcasts failed to reprocess:")
        for name, error in failed_to_process:
            logger.warning(f"- {name}: {error}")
            print(f"Failed to reprocess podcast {name}: {error}", file=sys.stderr)
        sys.exit(1)
    print("Reprocessing completed succesfully.")


if __name__ == "__main__":
    asyncio.run(main())
