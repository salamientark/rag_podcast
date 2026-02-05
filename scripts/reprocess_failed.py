#!/usr/bin/env python3
"""
Script to reprocess failed episodes (ProcessingStage.ERROR).
"""

import sys
import argparse
import asyncio
import logging
from collections import defaultdict
from typing import List, Dict, Any, Optional

# Add project root to sys.path if running from scripts directory
import os

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


def get_failed_episodes(limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Get failed episodes from database.
    Returns list of dicts with necessary info to avoid detachment issues.
    """
    with get_db_session() as session:
        query = session.query(Episode).filter(
            Episode.processing_stage == ProcessingStage.ERROR
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

    if args.dry_run:
        logger.info("DRY RUN MODE ENABLED")
        print("DRY RUN MODE ENABLED - No changes will be made")

    limit = None if args.all else args.limit
    logger.info(f"Mode: {'ALL' if args.all else f'Limit {limit}'}")

    try:
        failed_episodes = get_failed_episodes(limit)
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
    for p_id, ep_ids in episodes_by_podcast.items():
        p_info = podcasts_info[p_id]
        
        logger.info(
            f"Processing {len(ep_ids)} episodes for podcast '{p_info['name']}' (ID: {p_id})"
        )
        logger.info(f"Episode IDs: {ep_ids}")

        if args.dry_run:
            continue

        try:
            await run_pipeline(
                episodes_id=ep_ids,
                podcast_id=p_id,
                podcast_name=p_info["name"],
                feed_url=p_info["feed_url"],
                use_cloud_storage=True,
                force=True,  # Must force to reprocess ERROR stage
                verbose=True,
            )
        except Exception as e:
            logger.error(
                f"Failed to reprocess podcast {p_info['name']}: {e}", exc_info=True
            )
            print(f"Failed to reprocess podcast {p_info['name']}: {e}", file=sys.stderr)

    logger.info("=== REPROCESS COMPLETED ===")
    print("Reprocessing completed.")


if __name__ == "__main__":
    asyncio.run(main())
