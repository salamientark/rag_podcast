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
    uv run -m src.pipeline --full
    uv run -m src.pipeline --episode-id 672
    uv run -m src.pipeline --episode-id 672 680 685
    uv run -m src.pipeline --limit 5
    uv run -m src.pipeline --stages download,transcribe --limit 10
    uv run -m src.pipeline --dry-run --verbose

Examples:
    # Process all episodes end-to-end
    uv run -m src.pipeline --full

    # Process single episode
    uv run -m src.pipeline --episode-id 672

    # Process multiple specific episodes
    uv run -m src.pipeline --episode-id 672 680 685 690

    # Process last 5 episodes that need work
    uv run -m src.pipeline --limit 5

    # Process only specific stages for last 10 episodes
    uv run -m src.pipeline --stages transcribe,embed --limit 10

    # Force reprocessing from beginning
    uv run -m src.pipeline --episode-id 672 --force

    # Dry run to see what would be processed
    uv run -m src.pipeline --dry-run --limit 10 --verbose
"""

import sys
import argparse
from typing import List, Optional

from src.logger import setup_logging
from src.db.database import get_db_session
from src.db.models import Episode, ProcessingStage
from .orchestrator import run_pipeline


def validate_episode_ids(episode_ids: List[int]) -> tuple[List[int], List[int]]:
    """
    Validate that episode IDs exist in the database.

    Args:
        episode_ids: List of episode IDs to validate

    Returns:
        Tuple of (valid_ids, invalid_ids)
    """
    valid_ids = []
    invalid_ids = []

    try:
        with get_db_session() as session:
            for episode_id in episode_ids:
                episode = session.query(Episode).filter_by(id=episode_id).first()
                if episode:
                    valid_ids.append(episode_id)
                else:
                    invalid_ids.append(episode_id)
    except Exception as e:
        print(f"✗ Database error during validation: {e}", file=sys.stderr)
        sys.exit(1)

    return valid_ids, invalid_ids


def validate_stages(stage_names: List[str]) -> tuple[List[ProcessingStage], List[str]]:
    """
    Validate stage names against CLI stage names that map to orchestrator.

    Args:
        stage_names: List of stage names (strings)

    Returns:
        Tuple of (valid_stages, invalid_names)
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
    Count episodes at each processing stage.

    Returns:
        Dict mapping stage name to episode count
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


def print_dry_run_summary(args: argparse.Namespace, logger) -> None:
    """
    Print dry-run summary showing what would be processed.

    Args:
        args: Parsed command-line arguments
        logger: Logger instance
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

    # Validation check
    if args.episode_id:
        print("Validating episode IDs...")
        valid_ids, invalid_ids = validate_episode_ids(args.episode_id)
        if valid_ids:
            print(f"  ✓ Valid IDs ({len(valid_ids)}): {', '.join(map(str, valid_ids))}")
        if invalid_ids:
            print(
                f"  ✗ Invalid IDs ({len(invalid_ids)}): {', '.join(map(str, invalid_ids))}"
            )
            print("    These episodes do not exist in the database")

    print()
    print("=" * 80)
    print("End of dry run - no changes made")
    print("=" * 80)


def parse_arguments() -> argparse.Namespace:
    """
    Parse command-line arguments.

    Returns:
        Parsed arguments namespace
    """
    parser = argparse.ArgumentParser(
        description="Podcast Processing Pipeline - Orchestrates RSS sync, audio download, transcription, chunking, and embedding",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Processing Modes (choose one, default: --limit 5):
  --full            Process all episodes in database
  --episode-id      Process specific episode(s) by ID (can specify multiple)
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

Examples:
  # Process all episodes end-to-end
  uv run -m src.pipeline --full

  # Process single episode
  uv run -m src.pipeline --episode-id 672

  # Process multiple specific episodes
  uv run -m src.pipeline --episode-id 672 680 685 690

  # Process last 5 episodes needing work
  uv run -m src.pipeline --limit 5

  # Only transcribe and embed (skip download)
  uv run -m src.pipeline --stages raw_transcript,format_transcript,embed --limit 10

  # Force reprocessing from beginning
  uv run -m src.pipeline --episode-id 672 --force

  # Dry run to preview
  uv run -m src.pipeline --dry-run --limit 10 --verbose

Notes:
  - Pipeline automatically skips completed stages (unless --force)
  - Pipeline continues on error by default
  - Database tracks processing status for each episode
  - Logs written to logs/pipeline.log
  - Default behavior (no args): processes up to 5 episodes needing work
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

    return parser.parse_args()


def main():
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

    # Validate episode IDs if provided
    if args.episode_id:
        logger.info(f"Validating {len(args.episode_id)} episode ID(s)")
        valid_ids, invalid_ids = validate_episode_ids(args.episode_id)

        if invalid_ids:
            print(
                f"✗ Error: The following episode IDs do not exist in database: {', '.join(map(str, invalid_ids))}",
                file=sys.stderr,
            )
            logger.error(f"Invalid episode IDs: {invalid_ids}")
            sys.exit(1)

        if not valid_ids:
            print("✗ Error: No valid episode IDs provided", file=sys.stderr)
            sys.exit(1)

        logger.info(f"All {len(valid_ids)} episode ID(s) validated successfully")

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
        run_pipeline(
            episodes_id=episodes_id,
            limit=limit,
            stages=args.stages,
            dry_run=args.dry_run,
            verbose=args.verbose,
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
    main()
