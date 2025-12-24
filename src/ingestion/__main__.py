#!/usr/bin/env python3
"""
Main entry point for the ingestion package.

This allows running the sync_episodes script as a module with:
    uv run -m src.ingestion.sync_episodes

By default, if you run just:
    uv run -m src.ingestion

It will run the sync_episodes script as the default ingestion operation.
"""

import argparse
import sys
from datetime import datetime, timedelta

from src.db import get_db_session, Episode
from src.logger import setup_logging
from src.ingestion.sync_episodes import (
    fetch_podcast_episodes,
    filter_episodes,
    sync_to_database,
)


def main():
    """
    Entry point for the ingestion CLI that synchronizes podcast episodes from an RSS feed into the database.

    Parses command-line arguments (e.g., --full-sync, --days, --limit, --dry-run, --feed-url, --reconcile, --verbose) and runs one of two workflows:
    - Reconciliation: iterates database episodes to reconcile state from the filesystem (currently raises NotImplementedError).
    - RSS sync: fetches episodes from the configured or provided feed URL, filters and synchronizes them to the database, and prints a summary.

    Exits the process with code 0 on success, 1 on error, or 130 when interrupted by the user.
    """
    parser = argparse.ArgumentParser(
        description="Sync podcast episodes from RSS feed to database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  uv run -m src.ingestion.sync_episodes                  # Sync last 30 days
  uv run -m src.ingestion.sync_episodes --full-sync      # Sync all episodes
  uv run -m src.ingestion.sync_episodes --feed-url https://feeds.example.com/podcast.xml  # Custom feed URL
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
        "--feed-url",
        type=str,
        default=None,
        help="RSS feed URL (overrides FEED_URL from .env)",
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
            # TODO: Fix broken import - reconcile_episode_status not found
            raise NotImplementedError("Reconcile functionality is currently broken")

        else:
            # EXISTING RSS SYNC WORKFLOW
            # Fetch episodes
            episodes = fetch_podcast_episodes(feed_url=args.feed_url)
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
