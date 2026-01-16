#!/usr/bin/env python3
"""
Main entry point for the ingestion package.

This allows running the sync_episodes script as a module with:
    uv run -m src.ingestion --podcast rdv-tech

By default, if you run just:
    uv run -m src.ingestion --podcast <name-or-slug>

It will sync episodes from the podcast's RSS feed to the database.
"""

import argparse
import sys
from datetime import datetime, timedelta

from src.db import (
    get_db_session,
    Episode,
    get_podcast_by_name_or_slug,
    get_all_podcasts,
    create_podcast,
)
from src.logger import setup_logging
from src.ingestion.sync_episodes import (
    fetch_podcast_episodes,
    filter_episodes,
    sync_to_database,
    generate_slug,
)


def get_or_create_podcast(podcast_identifier: str):
    """
    Get existing podcast or prompt to create a new one.

    Args:
        podcast_identifier: Podcast name or slug to look up.

    Returns:
        Podcast object if found or created.

    Raises:
        SystemExit: If user cancels podcast creation.
    """
    podcast = get_podcast_by_name_or_slug(podcast_identifier)

    if podcast:
        return podcast

    # Podcast not found - show existing options and prompt for feed URL
    print(f"\nPodcast '{podcast_identifier}' not found in database.")
    print("\nExisting podcasts:")
    for p in get_all_podcasts():
        print(f"  - {p.name} (slug: {p.slug})")

    print(f"\nTo add '{podcast_identifier}' as a new podcast, enter its RSS feed URL.")
    print("Press Ctrl+C to cancel.\n")

    try:
        feed_url = input("Feed URL: ").strip()
        if not feed_url:
            print("Feed URL is required.")
            sys.exit(1)

        # Generate slug from identifier
        slug = generate_slug(podcast_identifier)

        # Create new podcast
        podcast = create_podcast(
            name=podcast_identifier,
            slug=slug,
            feed_url=feed_url,
        )
        # Note: using print here since we're in an interactive prompt context
        print(f"Created podcast: {podcast.name} (slug: {podcast.slug})")
        return podcast

    except KeyboardInterrupt:
        print("\nCancelled.")
        sys.exit(130)


def main():
    """
    Entry point for the ingestion CLI that synchronizes podcast episodes from an RSS feed into the database.

    Parses command-line arguments and syncs episodes from the podcast's RSS feed to the database.

    Exits the process with code 0 on success, 1 on error, or 130 when interrupted by the user.
    """
    parser = argparse.ArgumentParser(
        description="Sync podcast episodes from RSS feed to database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  uv run -m src.ingestion --podcast rdv-tech              # Sync last 30 days
  uv run -m src.ingestion --podcast "Le rendez-vous Tech" # Sync using full name
  uv run -m src.ingestion --podcast rdv-tech --full-sync  # Sync all episodes
  uv run -m src.ingestion --podcast rdv-tech --days 60    # Sync last 60 days
  uv run -m src.ingestion --podcast rdv-tech --limit 5    # Sync 5 most recent
  uv run -m src.ingestion --podcast rdv-tech --dry-run    # Test mode (fast)
        """,
    )

    parser.add_argument(
        "--podcast",
        type=str,
        required=True,
        help="Podcast name or slug (case-insensitive)",
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
        # Get or create podcast
        podcast = get_or_create_podcast(args.podcast)
        logger.info(f"Using podcast: {podcast.name} (id={podcast.id})")

        # Validate reconcile usage
        if args.reconcile and not (args.full_sync or args.limit):
            parser.error("--reconcile requires either --full-sync or --limit")

        if args.reconcile:
            # RECONCILIATION WORKFLOW: Query database and reconcile from filesystem
            print("Running reconciliation from filesystem...")

            with get_db_session() as session:
                query = session.query(Episode).filter_by(podcast_id=podcast.id)
                query = query.order_by(Episode.published_date.desc())

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
            # RSS SYNC WORKFLOW
            # Fetch episodes from RSS feed
            episodes = fetch_podcast_episodes(feed_url=podcast.feed_url)
            if not episodes:
                print("No episodes found")
                return

            # Filter episodes
            episodes = filter_episodes(episodes, args.full_sync, args.days, args.limit)

            # Sync to database with podcast_id
            stats = sync_to_database(
                episodes, podcast_id=podcast.id, dry_run=args.dry_run
            )

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
