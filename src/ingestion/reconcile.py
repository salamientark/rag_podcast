#!/usr/bin/env python3
"""
Episode Database Reconciliation Script

Reconciles episode database records with actual filesystem state and Qdrant embeddings.
This script ensures database fields are up-to-date by:
  - Scanning filesystem for episode files (audio, transcripts, mappings)
  - Extracting metadata from transcript JSON files
  - Verifying embeddings in Qdrant vector database
  - Updating episode processing stages accordingly

Usage:
    uv run -m src.ingestion.reconcile --all                                     # Reconcile all episodes
    uv run -m src.ingestion.reconcile --podcast "Lex Fridman Podcast"           # All episodes from podcast
    uv run -m src.ingestion.reconcile --podcast "Lex Fridman Podcast" --episodes 670 671  # Specific episodes
    uv run -m src.ingestion.reconcile --days 7                                  # Recent episodes (all podcasts)
    uv run -m src.ingestion.reconcile --podcast "Lex Fridman Podcast" --days 7  # Recent from podcast
    uv run -m src.ingestion.reconcile --dry-run --all                           # Test mode
    uv run -m src.ingestion.reconcile --all --skip-qdrant                       # Filesystem only
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Any

from dotenv import load_dotenv

from src.db import get_db_session, Episode
from src.db.models import ProcessingStage
from src.db.qdrant_client import get_qdrant_client, check_episode_exists_in_qdrant
from src.logger import setup_logging, log_function


# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Init logger
logger = setup_logging(logger_name="reconcile", log_file="logs/reconcile.log")


# ============ HELPER FUNCTIONS ============
@log_function(logger_name="reconcile", log_execution_time=True)
def find_episode_file(episode_id: int, file_dir: Path, pattern: str) -> Optional[Path]:
    """
    Find episode file using glob pattern to locate audio and transcript files.

    Args:
        episode_id: The database ID of the episode to search for
        file_dir: Directory path to search within
        pattern: Glob pattern to match files (e.g., "episode_001_*.mp3")

    Returns:
        Path object if exactly one valid file is found, None otherwise
        Returns None if no files match, multiple files match, or file is empty
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
    formatted_exists: bool,
    embedded_in_qdrant: bool = False,
) -> ProcessingStage:
    """
    Determine highest processing stage based on which files and embeddings exist.

    Args:
        audio_exists: True if audio file exists on disk
        raw_exists: True if raw transcript JSON file exists on disk
        formatted_exists: True if formatted transcript TXT file exists on disk
        embedded_in_qdrant: True if episode is found in Qdrant vector database

    Returns:
        ProcessingStage enum representing the maximum stage that can be
        proven by existing files and embeddings. Stages are ordered from SYNCED to EMBEDDED.
    """
    # Check highest stage first
    if embedded_in_qdrant and formatted_exists and raw_exists and audio_exists:
        return ProcessingStage.EMBEDDED
    elif formatted_exists and raw_exists and audio_exists:
        return ProcessingStage.FORMATTED_TRANSCRIPT
    elif raw_exists and audio_exists:
        return ProcessingStage.RAW_TRANSCRIPT
    elif audio_exists:
        return ProcessingStage.AUDIO_DOWNLOADED
    else:
        return ProcessingStage.SYNCED


@log_function(logger_name="reconcile", log_execution_time=True)
def extract_transcript_metadata(raw_transcript_path: Path) -> Optional[dict[str, Any]]:
    """
    Extract metadata from AssemblyAI raw transcript JSON.

    Reads JSON structure:
    {
        "transcript": {
            "confidence": 0.791765,
            "audio_duration": 3335
        }
    }

    Args:
        raw_transcript_path: Path to raw_episode_{id}.json file

    Returns:
        Dict with 'duration' (int, seconds) and 'confidence' (float, 0-1)
        Returns None if file cannot be parsed or is missing required fields

    Raises:
        None - logs errors and returns None on failure
    """
    try:
        with open(raw_transcript_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        transcript = data.get("transcript", {})

        # Extract required fields
        duration = transcript.get("audio_duration")
        confidence = transcript.get("confidence")

        if duration is None or confidence is None:
            logger.warning(
                f"Missing required fields in {raw_transcript_path.name}: "
                f"duration={duration}, confidence={confidence}"
            )
            return None

        return {
            "duration": int(duration),
            "confidence": float(confidence),
        }

    except (json.JSONDecodeError, FileNotFoundError, KeyError) as e:
        logger.error(f"Failed to parse metadata from {raw_transcript_path}: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error parsing {raw_transcript_path}: {e}")
        return None


# ============ RECONCILIATION FUNCTIONS ============
@log_function(logger_name="reconcile", log_execution_time=True)
def reconcile_filesystem(
    episodes: list[Episode],
    audio_dir: Path = Path("data/audio"),
    transcript_dir: Path = Path("data/transcripts"),
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Reconcile episode records with local filesystem state.

    For each episode, checks for:
    - Audio file: episode_{id}_{title}.mp3
    - Raw transcript: raw_episode_{id}.json (+ extracts duration/confidence)
    - Speaker mapping: speakers_episode_{id}.json
    - Formatted transcript: formatted_episode_{id}.txt

    Updates database fields:
    - audio_file_path
    - raw_transcript_path
    - speaker_mapping_path
    - formatted_transcript_path
    - transcript_duration (from JSON)
    - transcript_confidence (from JSON)
    - processing_stage (based on file existence)

    Args:
        episodes: List of Episode objects to reconcile
        audio_dir: Directory containing audio files
        transcript_dir: Directory containing transcript subdirectories
        dry_run: If True, don't commit changes to database

    Returns:
        Statistics dict with detailed field reconciliation counts
    """
    if not episodes:
        print("No episodes to reconcile")
        return {
            "processed": 0,
            "updated": 0,
            "unchanged": 0,
            "errors": 0,
            "fields_reconciled": {},
        }

    print(f"Reconciling {len(episodes)} episodes from filesystem...")

    stats = {
        "processed": 0,
        "updated": 0,
        "unchanged": 0,
        "errors": 0,
        "fields_reconciled": {
            "audio_file_path": 0,
            "raw_transcript_path": 0,
            "formatted_transcript_path": 0,
            "speaker_mapping_path": 0,
            "transcript_duration": 0,
            "transcript_confidence": 0,
            "processing_stage": 0,
        },
    }

    with get_db_session() as session:
        for episode in episodes:
            try:
                # Refresh episode to ensure it's attached to this session
                episode = session.merge(episode)

                episode_updated = False
                old_stage = episode.processing_stage

                # Find files using patterns
                episode_transcript_dir = (
                    transcript_dir / f"episode_{episode.episode_id:03d}"
                )

                # 1. Audio file
                audio_pattern = f"episode_{episode.episode_id:03d}_*.mp3"
                audio_path = find_episode_file(
                    episode.episode_id, audio_dir, audio_pattern
                )

                # 2. Raw transcript
                raw_pattern = f"raw_episode_{episode.episode_id}.json"
                raw_path = find_episode_file(
                    episode.episode_id, episode_transcript_dir, raw_pattern
                )

                # 3. Speaker mapping
                speaker_pattern = f"speakers_episode_{episode.episode_id}.json"
                speaker_path = find_episode_file(
                    episode.episode_id, episode_transcript_dir, speaker_pattern
                )

                # 4. Formatted transcript
                formatted_pattern = f"formatted_episode_{episode.episode_id}.txt"
                formatted_path = find_episode_file(
                    episode.episode_id, episode_transcript_dir, formatted_pattern
                )

                # Update paths with warnings for overwrites
                if audio_path:
                    if episode.audio_file_path != str(audio_path):
                        if episode.audio_file_path:
                            logger.warning(
                                f"Episode {episode.episode_id}: Overwriting audio_file_path "
                                f"from '{episode.audio_file_path}' to '{audio_path}'"
                            )
                        episode.audio_file_path = str(audio_path)
                        stats["fields_reconciled"]["audio_file_path"] += 1
                        episode_updated = True

                if raw_path:
                    if episode.raw_transcript_path != str(raw_path):
                        if episode.raw_transcript_path:
                            logger.warning(
                                f"Episode {episode.episode_id}: Overwriting raw_transcript_path "
                                f"from '{episode.raw_transcript_path}' to '{raw_path}'"
                            )
                        episode.raw_transcript_path = str(raw_path)
                        stats["fields_reconciled"]["raw_transcript_path"] += 1
                        episode_updated = True

                    # Extract metadata from raw transcript
                    metadata = extract_transcript_metadata(raw_path)
                    if metadata:
                        # Update duration
                        if episode.transcript_duration != metadata["duration"]:
                            episode.transcript_duration = metadata["duration"]
                            stats["fields_reconciled"]["transcript_duration"] += 1
                            episode_updated = True

                        # Update confidence
                        if episode.transcript_confidence != metadata["confidence"]:
                            episode.transcript_confidence = metadata["confidence"]
                            stats["fields_reconciled"]["transcript_confidence"] += 1
                            episode_updated = True

                if speaker_path:
                    if episode.speaker_mapping_path != str(speaker_path):
                        if episode.speaker_mapping_path:
                            logger.warning(
                                f"Episode {episode.episode_id}: Overwriting speaker_mapping_path "
                                f"from '{episode.speaker_mapping_path}' to '{speaker_path}'"
                            )
                        episode.speaker_mapping_path = str(speaker_path)
                        stats["fields_reconciled"]["speaker_mapping_path"] += 1
                        episode_updated = True

                if formatted_path:
                    if episode.formatted_transcript_path != str(formatted_path):
                        if episode.formatted_transcript_path:
                            logger.warning(
                                f"Episode {episode.episode_id}: Overwriting formatted_transcript_path "
                                f"from '{episode.formatted_transcript_path}' to '{formatted_path}'"
                            )
                        episode.formatted_transcript_path = str(formatted_path)
                        stats["fields_reconciled"]["formatted_transcript_path"] += 1
                        episode_updated = True

                # Determine target stage (without Qdrant check for now)
                target_stage = determine_stage_for_file(
                    audio_exists=audio_path is not None,
                    raw_exists=raw_path is not None,
                    formatted_exists=formatted_path is not None,
                    embedded_in_qdrant=False,  # Will check in reconcile_qdrant
                )

                # Get stage ordering for comparison
                stage_order = list(ProcessingStage)
                current_stage_index = stage_order.index(episode.processing_stage)
                target_stage_index = stage_order.index(target_stage)

                # Only update if moving forward OR if current stage is EMBEDDED
                # (EMBEDDED stage will be verified separately in reconcile_qdrant)
                if target_stage_index > current_stage_index:
                    episode.processing_stage = target_stage
                    stats["fields_reconciled"]["processing_stage"] += 1
                    episode_updated = True

                # Commit changes
                if episode_updated:
                    if not dry_run:
                        session.commit()

                    # Print update summary
                    changes = []
                    if audio_path and episode.audio_file_path == str(audio_path):
                        changes.append("audio")
                    if raw_path and episode.raw_transcript_path == str(raw_path):
                        changes.append("raw_transcript")
                    if speaker_path and episode.speaker_mapping_path == str(
                        speaker_path
                    ):
                        changes.append("speaker_mapping")
                    if formatted_path and episode.formatted_transcript_path == str(
                        formatted_path
                    ):
                        changes.append("formatted_transcript")

                    stage_change = ""
                    if old_stage != episode.processing_stage:
                        stage_change = (
                            f" ({old_stage.value} → {episode.processing_stage.value})"
                        )

                    print(
                        f"  ✓ Episode {episode.episode_id}: {', '.join(changes)}{stage_change}"
                    )
                    logger.info(f"Updated episode {episode.episode_id}: {changes}")
                    stats["updated"] += 1
                else:
                    print(
                        f"  - Episode {episode.episode_id}: No update needed (stage: {episode.processing_stage.value})"
                    )
                    stats["unchanged"] += 1

                stats["processed"] += 1

            except Exception as e:
                print(f"  ✗ Error reconciling episode {episode.episode_id}: {e}")
                logger.error(f"Error reconciling episode {episode.episode_id}: {e}")
                stats["errors"] += 1

    return stats


@log_function(logger_name="reconcile", log_execution_time=True)
def reconcile_qdrant(
    episodes: list[Episode],
    collection_name: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Reconcile episode embedding status with Qdrant vector database.

    Checks Qdrant to verify which episodes have embeddings and updates
    processing_stage to EMBEDDED if:
    - Episode has formatted_transcript_path set
    - Episode is found in Qdrant collection

    Also detects mismatches (episodes marked EMBEDDED but not in Qdrant)
    and downgrades them to the appropriate filesystem-based stage.

    Error Handling:
    - If Qdrant unreachable → skip verification, return early with error flag
    - If collection doesn't exist → skip verification, log warning

    Args:
        episodes: List of Episode objects to check
        collection_name: Qdrant collection name to query
        dry_run: If True, don't commit changes to database

    Returns:
        Statistics dict with Qdrant verification results
    """
    stats = {
        "checked": 0,
        "found_embedded": 0,
        "updated_to_embedded": 0,
        "downgraded": 0,
        "skipped": 0,
        "error": None,
    }

    if not episodes:
        return stats

    print(f"Verifying embeddings in Qdrant (collection: {collection_name})...")

    try:
        with get_qdrant_client() as client:
            # Check if collection exists
            if not client.collection_exists(collection_name=collection_name):
                logger.warning(f"Qdrant collection '{collection_name}' does not exist")
                stats["error"] = f"Collection '{collection_name}' not found"
                stats["skipped"] = len(episodes)
                print(
                    f"  ⚠️  Collection '{collection_name}' not found, skipping verification"
                )
                return stats

            with get_db_session() as session:
                for episode in episodes:
                    try:
                        # Refresh episode
                        episode = session.merge(episode)

                        # Only check episodes that could potentially be embedded
                        # (have at least a formatted transcript)
                        stage_order = list(ProcessingStage)
                        formatted_index = stage_order.index(
                            ProcessingStage.FORMATTED_TRANSCRIPT
                        )
                        current_index = stage_order.index(episode.processing_stage)

                        if current_index < formatted_index:
                            # Episode not ready for embedding yet
                            continue

                        stats["checked"] += 1

                        # Check if episode exists in Qdrant
                        exists_in_qdrant = check_episode_exists_in_qdrant(
                            client, collection_name, episode.episode_id
                        )

                        if exists_in_qdrant:
                            stats["found_embedded"] += 1

                            # Upgrade to EMBEDDED if not already
                            if episode.processing_stage != ProcessingStage.EMBEDDED:
                                old_stage = episode.processing_stage
                                episode.processing_stage = ProcessingStage.EMBEDDED

                                if not dry_run:
                                    session.commit()

                                print(
                                    f"  ✓ Episode {episode.episode_id}: Found in Qdrant → EMBEDDED (was {old_stage.value})"
                                )
                                stats["updated_to_embedded"] += 1
                            else:
                                print(
                                    f"  ✓ Episode {episode.episode_id}: Found in Qdrant, already EMBEDDED"
                                )
                        else:
                            # Episode NOT in Qdrant
                            if episode.processing_stage == ProcessingStage.EMBEDDED:
                                # Downgrade to filesystem-appropriate stage
                                target_stage = determine_stage_for_file(
                                    audio_exists=bool(episode.audio_file_path),
                                    raw_exists=bool(episode.raw_transcript_path),
                                    formatted_exists=bool(
                                        episode.formatted_transcript_path
                                    ),
                                    embedded_in_qdrant=False,
                                )

                                episode.processing_stage = target_stage

                                if not dry_run:
                                    session.commit()

                                print(
                                    f"  ⚠️  Episode {episode.episode_id}: NOT in Qdrant, downgraded EMBEDDED → {target_stage.value}"
                                )
                                logger.warning(
                                    f"Episode {episode.episode_id} marked EMBEDDED but not found in Qdrant, "
                                    f"downgraded to {target_stage.value}"
                                )
                                stats["downgraded"] += 1
                            else:
                                print(
                                    f"  - Episode {episode.episode_id}: Not yet embedded"
                                )

                    except Exception as e:
                        logger.error(
                            f"Error checking episode {episode.episode_id} in Qdrant: {e}"
                        )
                        stats["errors"] = stats.get("errors", 0) + 1

    except Exception as e:
        logger.error(f"Qdrant connection failed: {e}")
        stats["error"] = str(e)
        stats["skipped"] = len(
            [
                ep
                for ep in episodes
                if list(ProcessingStage).index(ep.processing_stage)
                >= list(ProcessingStage).index(ProcessingStage.FORMATTED_TRANSCRIPT)
            ]
        )
        print(f"  ⚠️  Qdrant connection failed: {e}")
        print(f"      Skipping verification for {stats['skipped']} episodes")
        return stats

    return stats


def print_reconciliation_summary(fs_stats: dict, qdrant_stats: dict) -> None:
    """
    Print a comprehensive, formatted summary of reconciliation results.

    Displays:
    - Episode counts (processed, updated, unchanged, errors)
    - Field-by-field reconciliation counts
    - Qdrant verification results
    - Any warnings or mismatches detected

    Args:
        fs_stats: Statistics from filesystem reconciliation
        qdrant_stats: Statistics from Qdrant reconciliation
    """
    print("\nRECONCILIATION SUMMARY")
    print("=" * 60)

    # Episodes summary
    print("\nEpisodes:")
    print(f"  Total processed:  {fs_stats['processed']}")
    print(f"  Updated:          {fs_stats['updated']}")
    print(f"  Unchanged:        {fs_stats['unchanged']}")
    if fs_stats["errors"] > 0:
        print(f"  Errors:           {fs_stats['errors']}")

    # Filesystem fields
    print("\nFilesystem Fields Reconciled:")
    fields = fs_stats.get("fields_reconciled", {})
    if fields:
        for field, count in fields.items():
            print(f"  {field:30s} {count} episodes")

    # Qdrant verification
    if qdrant_stats:
        print("\nQdrant Verification:")
        if qdrant_stats.get("error"):
            print(f"  ⚠️  SKIPPED: {qdrant_stats['error']}")
            print(f"      {qdrant_stats['skipped']} episodes not verified")
        else:
            print(f"  Checked:                      {qdrant_stats['checked']} episodes")
            print(
                f"  Found embedded:               {qdrant_stats['found_embedded']} episodes"
            )
            if qdrant_stats["updated_to_embedded"] > 0:
                print(
                    f"  Updated to EMBEDDED:          {qdrant_stats['updated_to_embedded']} episodes"
                )
            if qdrant_stats["downgraded"] > 0:
                print(
                    f"  ⚠️  Downgraded (not in Qdrant): {qdrant_stats['downgraded']} episodes"
                )

    print()


# ============ CLI ENTRY POINT ============
def main():
    """Main CLI entry point with argument parsing"""
    parser = argparse.ArgumentParser(
        description="Reconcile episode database with filesystem and Qdrant",
        epilog="""
Examples:
  # Reconcile all episodes
  uv run -m src.ingestion.reconcile --all

  # Reconcile all episodes from a specific podcast
  uv run -m src.ingestion.reconcile --podcast "Lex Fridman Podcast"

  # Reconcile specific episodes from a podcast
  uv run -m src.ingestion.reconcile --podcast "Lex Fridman Podcast" --episodes 670 671 672

  # Reconcile episodes from last 7 days from a podcast
  uv run -m src.ingestion.reconcile --podcast "Lex Fridman Podcast" --days 7

  # Reconcile episodes from last 7 days (all podcasts)
  uv run -m src.ingestion.reconcile --days 7

  # Dry run (no database changes)
  uv run -m src.ingestion.reconcile --all --dry-run

  # Skip Qdrant verification
  uv run -m src.ingestion.reconcile --all --skip-qdrant
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--all",
        action="store_true",
        help="Reconcile ALL episodes in the database (use with caution)",
    )
    parser.add_argument(
        "--episodes",
        type=int,
        nargs="+",
        metavar="ID",
        help="Specific episode IDs to reconcile (e.g., --episodes 670 671 672)",
    )
    parser.add_argument(
        "--days",
        type=int,
        metavar="N",
        help="Reconcile episodes updated in the last N days",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without committing to database",
    )
    parser.add_argument(
        "--skip-qdrant",
        action="store_true",
        help="Skip Qdrant verification (filesystem reconciliation only)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging output",
    )
    parser.add_argument(
        "--podcast",
        type=str,
        metavar="NAME",
        help="Filter episodes by podcast name (case-insensitive)",
    )

    args = parser.parse_args()

    # Mutual exclusivity check
    if not (args.all or args.episodes or args.days or args.podcast):
        parser.error(
            "Please specify episodes to reconcile: --all, --podcast, --episodes, or --days"
        )

    # Setup logging
    global logger
    logger = setup_logging(
        logger_name="reconcile", log_file="logs/reconcile.log", verbose=args.verbose
    )

    # Load environment variables
    load_dotenv()

    # Fetch episodes to reconcile
    print(f"\n{'=' * 60}")
    print("EPISODE RECONCILIATION")
    print(f"{'=' * 60}")

    with get_db_session() as session:
        if args.episodes:
            # Specific episodes
            query = session.query(Episode).filter(Episode.episode_id.in_(args.episodes))
            if args.podcast:
                query = query.filter(Episode.podcast.ilike(args.podcast))
            episodes = query.all()
            print(f"Mode: Specific episodes ({args.episodes})")
            if args.podcast:
                print(f"      Filtered by podcast: {args.podcast}")
        elif args.days:
            # Recent episodes
            cutoff = datetime.now() - timedelta(days=args.days)
            query = session.query(Episode).filter(Episode.updated_at >= cutoff)
            if args.podcast:
                query = query.filter(Episode.podcast.ilike(args.podcast))
            episodes = query.all()
            print(f"Mode: Episodes from last {args.days} days")
            if args.podcast:
                print(f"      Filtered by podcast: {args.podcast}")
        else:
            # All episodes (or filtered by podcast only)
            query = session.query(Episode)
            if args.podcast:
                query = query.filter(Episode.podcast.ilike(args.podcast))
                episodes = query.all()
                print(f"Mode: ALL episodes from podcast '{args.podcast}'")
            else:
                episodes = query.all()
                print("Mode: ALL episodes")

    if not episodes:
        print("No episodes found to reconcile")
        print(f"{'=' * 60}\n")
        return 0

    print(f"Episodes to process: {len(episodes)}")
    if args.dry_run:
        print("⚠️  DRY RUN MODE: No database changes will be committed")
    if args.skip_qdrant:
        print("⚠️  Skipping Qdrant verification")
    print(f"{'=' * 60}\n")

    # Step 1: Filesystem reconciliation
    print("📁 FILESYSTEM RECONCILIATION")
    print("-" * 60)
    fs_stats = reconcile_filesystem(episodes=episodes, dry_run=args.dry_run)

    # Step 2: Qdrant reconciliation (if not skipped)
    qdrant_stats = {}
    if not args.skip_qdrant:
        print("\n🔍 QDRANT VERIFICATION")
        print("-" * 60)
        collection_name = os.getenv("QDRANT_COLLECTION_NAME")
        if not collection_name:
            print(
                "⚠️  QDRANT_COLLECTION_NAME not set in .env, skipping Qdrant verification"
            )
        else:
            qdrant_stats = reconcile_qdrant(
                episodes=episodes, collection_name=collection_name, dry_run=args.dry_run
            )

    # Print summary
    print(f"\n{'=' * 60}")
    print_reconciliation_summary(fs_stats, qdrant_stats)

    if args.dry_run:
        print("✅ Dry run complete - no changes were committed\n")
    else:
        print("✅ Reconciliation complete!\n")

    print(f"{'=' * 60}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
