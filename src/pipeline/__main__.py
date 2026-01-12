#!/usr/bin/env python3
"""
CLI interface for the podcast processing pipeline.

This pipeline orchestrates the complete workflow from RSS feed to vector embeddings:
    1. Sync episodes from RSS feed
    2. Download audio files
    3. Transcribe with speaker diarization
    4. Chunk transcripts for RAG
    5. Generate and store embeddings in Qdrant

Usage:
    uv run -m src.pipeline --podcast "Le rendez-vous Tech" --full
    uv run -m src.pipeline --feed-url "https://feeds.example.com/podcast.xml" --limit 5
    uv run -m src.pipeline --podcast "Le rendez-vous Tech" --episode-id 672
    uv run -m src.pipeline --feed-url "https://feeds.example.com/podcast.xml" --episode-id 672 680

Examples:
    # Using podcast name
    uv run -m src.pipeline --podcast "Le rendez-vous Tech" --full
    uv run -m src.pipeline --podcast "Le rendez-vous Tech" --limit 5
    uv run -m src.pipeline --podcast "Le rendez-vous Tech" --episode-id 672 680

    # Using custom feed URL (auto-detects podcast name, always syncs)
    uv run -m src.pipeline --feed-url "https://feeds.example.com/podcast.xml" --full
    uv run -m src.pipeline --feed-url "https://feeds.example.com/podcast.xml" --limit 5
    uv run -m src.pipeline --feed-url "https://feeds.example.com/podcast.xml" --episode-id 672

    # Other options
    uv run -m src.pipeline --podcast "Le rendez-vous Tech" --stages transcribe,embed --limit 10
    uv run -m src.pipeline --podcast "Le rendez-vous Tech" --episode-id 672 --force
    uv run -m src.pipeline --feed-url "https://feeds.example.com/podcast.xml" --dry-run --verbose
"""

import sys
import argparse
import asyncio
from typing import List, Optional

from src.logger import setup_logging
from src.db.database import get_db_session
from src.db.models import Episode, ProcessingStage
from .orchestrator import run_pipeline


def validate_stages(stage_names: List[str]) -> tuple[List[ProcessingStage], List[str]]:
    """
    Map CLI stage name strings to their corresponding ProcessingStage enum values.

    Parameters:
        stage_names (List[str]): Iterable of stage names provided via the CLI (e.g., "sync", "download", "raw_transcript", "format_transcript", "embed").

    Returns:
        tuple[List[ProcessingStage], List[str]]: A pair where the first element is a list of recognized ProcessingStage enum values in the same order as valid input names, and the second element is a list of input names that were not recognized.
    """
    valid_stages = []
    invalid_names = []

    # CLI stage names that match orchestrator expectations
    cli_to_enum_map = {
        "sync": ProcessingStage.SYNCED,
        "download": ProcessingStage.AUDIO_DOWNLOADED,
        "raw_transcript": ProcessingStage.RAW_TRANSCRIPT,
        "format_transcript": ProcessingStage.FORMATTED_TRANSCRIPT,
        "embed": ProcessingStage.EMBEDDED,
    }

    for name in stage_names:
        if name in cli_to_enum_map:
            valid_stages.append(cli_to_enum_map[name])
        else:
            invalid_names.append(name)

    return valid_stages, invalid_names


def count_episodes_by_stage() -> dict:
    """
    Count episodes grouped by processing stage.

    Returns:
        dict: Mapping from `ProcessingStage.value` (stage name) to the integer count of `Episode` records in that stage. Returns an empty dict and prints an error to stderr if a database error occurs.
    """
    try:
        with get_db_session() as session:
            counts = {}
            for stage in ProcessingStage:
                count = session.query(Episode).filter_by(processing_stage=stage).count()
                counts[stage.value] = count
            return counts
    except Exception as e:
        print(f"✗ Database error during stage counting: {e}", file=sys.stderr)
        return {}


def get_available_podcasts() -> list[str]:
    """
    Return the list of available podcast names from the database.

    If retrieval fails, prints an error message to stderr and returns an empty list.

    Returns:
        list[str]: Podcast names from the database, or an empty list if retrieval fails.
    """
    try:
        from src.db import get_podcasts

        return get_podcasts()
    except Exception as e:
        print(f"✗ Error retrieving podcasts: {e}", file=sys.stderr)
        return []


def validate_podcast(podcast_name: str) -> tuple[bool, Optional[str]]:
    """
    Finds a canonical podcast name in the database that matches the provided name.

    Parameters:
        podcast_name (str): Podcast name to validate (case-insensitive).

    Returns:
        tuple[bool, Optional[str]]: `(True, canonical_name)` when a case-insensitive match is found; `(False, None)` otherwise.

    Notes:
        If no podcasts exist in the database or the name is not found, an error message is printed to stderr.
    """
    available_podcasts = get_available_podcasts()

    if not available_podcasts:
        print(
            "✗ Error: No podcasts found in database. Run sync first.", file=sys.stderr
        )
        return False, None

    # Case-insensitive search for matching podcast
    podcast_lower = podcast_name.lower()
    for db_podcast in available_podcasts:
        if db_podcast.lower() == podcast_lower:
            return True, db_podcast  # Return canonical DB name

    # Not found - show available podcasts
    print(f"✗ Error: Podcast '{podcast_name}' not found in database", file=sys.stderr)
    print("\nAvailable podcasts:", file=sys.stderr)
    for podcast in available_podcasts:
        print(f"  - {podcast}", file=sys.stderr)

    return False, None


def validate_mutually_exclusive_args(args: argparse.Namespace) -> Optional[str]:
    """
    Validate that mutually exclusive argument combinations are not used.
    Sets default behavior of --limit 5 if no mode is specified.

    Args:
        args: Parsed command-line arguments

    Returns:
        Error message if validation fails, None otherwise
    """
    mode_flags = [args.full, args.episode_id is not None, args.limit is not None]
    active_modes = sum(mode_flags)

    if active_modes == 0:
        # Set default behavior: --limit 5
        args.limit = 5
        return None

    if active_modes > 1:
        return "Cannot combine --full, --episode-id, and --limit (choose one)"

    return None


def validate_storage_args(args: argparse.Namespace) -> None:
    """
    Ensure a storage option is selected by defaulting to local when neither --local nor --cloud is provided.

    Parameters:
        args (argparse.Namespace): Parsed CLI namespace; may be mutated to set `args.local = True` when neither `args.local` nor `args.cloud` is truthy.
    """
    # If neither storage flag is specified, default to local
    if not args.local and not args.cloud:
        args.local = True


def validate_feed_url_podcast_exclusivity(args: argparse.Namespace) -> Optional[str]:
    """
    Validate mutual exclusivity between --feed-url and --podcast and require that one is provided.

    Parameters:
        args (argparse.Namespace): Parsed command-line arguments with `feed_url` and `podcast` attributes.

    Returns:
        str: Error message if validation fails, `None` otherwise.
    """
    if args.feed_url and args.podcast:
        return "Cannot use both --feed-url and --podcast (they are mutually exclusive)"

    if not args.feed_url and not args.podcast:
        return "Either --feed-url or --podcast must be provided"

    return None


def print_dry_run_summary(args: argparse.Namespace, logger) -> None:
    """
    Print a human-readable dry-run summary of the pipeline configuration and current database counts.

    The summary displays the selected processing mode (full, specific episode IDs, or limited), podcast or feed URL filter, chosen pipeline stages, runtime options (force, verbose, storage backend), and per-stage episode counts retrieved from the database. This function only prints information and does not perform any processing.

    Args:
        args (argparse.Namespace): Parsed command-line arguments.
        logger: Logger instance for recording the dry-run action.
    """
    print("=" * 80)
    print("DRY RUN - No processing will occur")
    print("=" * 80)
    print()

    # Determine mode
    if args.full:
        mode = "FULL SYNC"
        print(f"Mode: {mode}")
        print("  → Process all episodes in database")
    elif args.episode_id:
        mode = "SPECIFIC EPISODES"
        print(f"Mode: {mode}")
        print(f"  → Episode IDs: {', '.join(map(str, args.episode_id))}")
    elif args.limit:
        mode = "LIMITED"
        print(f"Mode: {mode}")
        print(f"  → Process up to {args.limit} episodes needing work")

    print()

    # Podcast/Feed filter
    if args.podcast:
        print(f"Podcast filter: {args.podcast}")
        print("  → Only process episodes from this podcast")
        print()
    elif args.feed_url:
        print(f"Feed URL: {args.feed_url}")
        print("  → Will sync from custom feed and auto-detect podcast name")
        print("  → Sync stage will always run")
        print()

    # Stage configuration
    if args.stages:
        print(f"Stages: {', '.join(args.stages)}")
        print("  → Only run specified stages")
    else:
        print("Stages: ALL")
        print("  → Run complete pipeline (sync → embed)")

    print()

    # Options
    print("Options:")
    print(f"  Force reprocessing: {args.force}")
    print(f"  Verbose logging: {args.verbose}")
    storage_type = "Cloud Storage" if args.cloud else "Local Filesystem"
    print(f"  Storage backend: {storage_type}")

    print()

    # Database stats
    print("Current Database Status:")
    stage_counts = count_episodes_by_stage()
    if stage_counts:
        total = sum(stage_counts.values())
        print(f"  Total episodes: {total}")
        for stage, count in stage_counts.items():
            print(f"    {stage}: {count}")
    else:
        print("  Unable to retrieve database statistics")

    print()
    print("=" * 80)
    print("End of dry run - no changes made")
    print("=" * 80)


def parse_arguments() -> argparse.Namespace:
    """
    Parse command-line arguments for the podcast processing pipeline.

    Configures processing mode (--full, --episode-id, --limit), stage selection (--stages),
    podcast selection (--podcast or --feed-url), storage options (--local, --cloud),
    and miscellaneous flags (--force, --dry-run, --verbose).

    Returns:
        argparse.Namespace: Parsed arguments with attributes:
            full, episode_id, limit, stages, podcast, feed_url, force, dry_run,
            verbose, local, cloud
    """
    parser = argparse.ArgumentParser(
        description="Podcast Processing Pipeline - Orchestrates RSS sync, audio download, transcription, chunking, and embedding",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Required Parameter (choose one):
  --podcast         Podcast name to process (case-insensitive)
  --feed-url        RSS feed URL to sync and process (auto-detects podcast name)

Note: --podcast and --feed-url are MUTUALLY EXCLUSIVE

Processing Modes (choose one, default: --limit 5):
  --full            Process all episodes from podcast
  --episode-id      Process specific episode(s) by ID
  --limit           Process up to N episodes needing work
  (default)         Process up to 5 episodes needing work (if no mode specified)

Stage Control:
  --stages          Run only specific stages (comma-separated)

Available Stages:
  sync                     Episode metadata in database
  download                 Audio file downloaded
  raw_transcript          Initial transcription complete
  format_transcript       Speaker-identified transcript ready
  embed                   Chunks embedded in Qdrant

Storage Options:
  --local                  Save files to local filesystem (default)
  --cloud                  Save files to cloud storage (DigitalOcean Spaces)

Examples:
  # Using podcast name
  uv run -m src.pipeline --podcast "Le rendez-vous Tech" --full
  uv run -m src.pipeline --podcast "Le rendez-vous Tech" --limit 5
  uv run -m src.pipeline --podcast "Le rendez-vous Tech" --episode-id 672 680

  # Using custom feed URL (auto-detects podcast name, always syncs)
  uv run -m src.pipeline --feed-url "https://feeds.example.com/podcast.xml" --full
  uv run -m src.pipeline --feed-url "https://feeds.example.com/podcast.xml" --limit 5
  uv run -m src.pipeline --feed-url "https://feeds.example.com/podcast.xml" --episode-id 672

  # With specific stages
  uv run -m src.pipeline --feed-url "https://feeds.example.com/podcast.xml" --stages embed --limit 10

  # Force reprocessing
  uv run -m src.pipeline --podcast "Le rendez-vous Tech" --episode-id 672 --force

  # Dry run
  uv run -m src.pipeline --feed-url "https://feeds.example.com/podcast.xml" --dry-run --verbose

  # Case-insensitive matching
  uv run -m src.pipeline --podcast "le rendez-vous tech" --limit 5

Notes:
  - Either --podcast or --feed-url is REQUIRED (mutually exclusive)
  - With --feed-url: podcast name is auto-extracted from feed, sync always runs first
  - With --podcast: uses default feed from .env, sync runs only if in --stages
  - Podcast name matching is case-insensitive
  - Episode IDs are per-podcast
  - Multiple podcasts can coexist in the same database
  - Pipeline automatically skips completed stages (unless --force)
  - Logs written to logs/pipeline.log
  - Default behavior (no mode): processes up to 5 episodes needing work
        """,
    )

    # Processing mode (mutually exclusive)
    mode_group = parser.add_argument_group(
        "processing mode (choose one, default: --limit 5)"
    )
    mode_group.add_argument(
        "--full",
        action="store_true",
        help="Process all episodes in database end-to-end",
    )
    mode_group.add_argument(
        "--episode-id",
        type=int,
        nargs="+",
        metavar="ID",
        help="Process specific episode(s) by database ID (can specify multiple: --episode-id 672 680 685)",
    )
    mode_group.add_argument(
        "--limit",
        type=int,
        metavar="N",
        help="Process up to N episodes that need work (incremental mode)",
    )

    # Stage control
    stage_group = parser.add_argument_group("stage control")
    stage_group.add_argument(
        "--stages",
        type=str,
        metavar="STAGE,...",
        help="Run only specific stages (comma-separated, e.g., 'raw_transcript,format_transcript,embed')",
    )

    # Options
    options_group = parser.add_argument_group("options")
    options_group.add_argument(
        "--podcast",
        type=str,
        metavar="NAME",
        help="Podcast name to process (case-insensitive, mutually exclusive with --feed-url)",
    )
    options_group.add_argument(
        "--feed-url",
        type=str,
        metavar="URL",
        help="RSS feed URL to sync and process (auto-detects podcast name, mutually exclusive with --podcast)",
    )
    options_group.add_argument(
        "--force",
        action="store_true",
        help="Force reprocessing of already completed stages",
    )
    options_group.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be processed without executing",
    )
    options_group.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging output",
    )

    # Storage options
    storage_group = parser.add_argument_group("storage options")
    storage_exclusive = storage_group.add_mutually_exclusive_group()
    storage_exclusive.add_argument(
        "--local",
        action="store_true",
        help="Save audio and transcripts to local filesystem (default)",
    )
    storage_exclusive.add_argument(
        "--cloud",
        action="store_true",
        help="Save audio and transcripts to cloud storage",
    )

    return parser.parse_args()


async def main():
    """Main entry point for the pipeline CLI."""
    args = parse_arguments()

    # Setup logging
    logger = setup_logging(
        logger_name="pipeline",
        log_file="logs/pipeline.log",
        verbose=args.verbose,
    )

    # Validate mutually exclusive arguments
    validation_error = validate_mutually_exclusive_args(args)
    if validation_error:
        print(f"✗ Error: {validation_error}", file=sys.stderr)
        print("Run with --help for usage information", file=sys.stderr)
        sys.exit(1)

    # Validate and set default storage arguments
    validate_storage_args(args)

    # Validate feed-url and podcast mutual exclusivity
    validation_error = validate_feed_url_podcast_exclusivity(args)
    if validation_error:
        print(f"✗ Error: {validation_error}", file=sys.stderr)
        print("Run with --help for usage information", file=sys.stderr)
        sys.exit(1)

    # Validate podcast name if provided (not needed for feed-url)
    if args.podcast:
        is_valid, canonical_podcast = validate_podcast(args.podcast)
        if not is_valid:
            sys.exit(1)
        # Use canonical database name for consistency
        args.podcast = canonical_podcast
        logger.info(f"Filtering by podcast: {canonical_podcast}")
    elif args.feed_url:
        logger.info(f"Using custom feed URL: {args.feed_url}")
        # Podcast name will be extracted during sync stage in orchestrator

    # Parse and validate stages if provided
    if args.stages:
        stage_names = [s.strip() for s in args.stages.split(",")]
        valid_stages, invalid_names = validate_stages(stage_names)
        if invalid_names:
            print(
                f"✗ Error: Invalid stage names: {', '.join(invalid_names)}",
                file=sys.stderr,
            )
            print(
                "Valid stages: sync, download, raw_transcript, format_transcript, embed",
                file=sys.stderr,
            )
            sys.exit(1)
        args.stages = stage_names  # Store validated stage names

    # Dry run mode - show what would happen
    if args.dry_run:
        logger.info("Running in dry-run mode (no changes will be made)")
        print_dry_run_summary(args, logger)
        sys.exit(0)

    # Log pipeline start
    logger.info("=" * 80)
    logger.info("Pipeline execution started")
    if args.full:
        logger.info("Mode: Full sync (all episodes)")
    elif args.episode_id:
        logger.info(f"Mode: Specific episodes - IDs: {args.episode_id}")
    elif args.limit:
        logger.info(f"Mode: Limited processing - up to {args.limit} episodes")

    if args.stages:
        logger.info(f"Stages: {', '.join(args.stages)}")
    else:
        logger.info("Stages: All (complete pipeline)")

    storage_type = "cloud" if args.cloud else "local"
    logger.info(f"Storage: {storage_type}")
    logger.info(f"Options: force={args.force}")
    logger.info("=" * 80)

    # Execute the pipeline
    try:
        # Determine episodes to process based on mode
        episodes_id = None
        limit = None

        if args.episode_id:
            episodes_id = args.episode_id
        elif args.limit:
            limit = args.limit
        # For --full mode, both remain None

        # Call the orchestrator
        await run_pipeline(
            episodes_id=episodes_id,
            limit=limit,
            stages=args.stages,
            dry_run=args.dry_run,
            verbose=args.verbose,
            use_cloud_storage=args.cloud,
            podcast=args.podcast,
            feed_url=args.feed_url,
            force=args.force,
        )

        logger.info("Pipeline execution completed successfully")
        print("\n" + "=" * 80)
        print("✓ PIPELINE COMPLETED SUCCESSFULLY")
        print("=" * 80)

    except Exception as e:
        logger.error(f"Pipeline execution failed: {e}")
        print(f"\n✗ PIPELINE FAILED: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
