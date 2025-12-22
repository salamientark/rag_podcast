#!/usr/bin/env python3
"""
CLI interface for transcription using AssemblyAI Universal-2 with diarization.
Processes single or multiple audio files sequentially with caching support.

Usage:
    uv run -m src.transcription <file1.mp3> [file2.mp3 ...]
    uv run -m src.transcription <file1.mp3> -o data/transcripts/
    uv run -m src.transcription <file1.mp3> --dry-run
    uv run -m src.transcription <file1.mp3> --force --no-db-update

Examples:
    # Single file with default output
    uv run -m src.transcription data/audio/episode_001_title.mp3

    # Multiple files
    uv run -m src.transcription data/audio/episode_001.mp3 data/audio/episode_002.mp3

    # Custom output directory
    uv run -m src.transcription episode_001.mp3 -o custom/output/

    # Dry run to check what would be processed
    uv run -m src.transcription episode_*.mp3 --dry-run

    # Force re-transcription even if formatted transcript exists
    uv run -m src.transcription episode_001.mp3 --force

    # Process without updating database
    uv run -m src.transcription episode_001.mp3 --no-db-update
"""

import sys
import argparse
from pathlib import Path
from typing import List, Dict, Any, Union, Optional
import logging

from src.transcription.transcript import (
    check_formatted_transcript_exists,
    get_episode_id_from_path,
)
from src.logger import setup_logging, log_function
from src.db.database import get_db_session
from src.db.models import Episode, ProcessingStage


def check_db_needs_update(episode_id: int, output_dir: Path) -> Dict[str, Any]:
    """
    Check if database record needs updating for an episode.

    Args:
        episode_id: Episode ID number
        output_dir: Base output directory

    Returns:
        Dict with 'exists', 'needs_update', and 'current_stage' keys
    """
    try:
        with get_db_session() as session:
            episode = session.query(Episode).filter_by(id=episode_id).first()

            if not episode:
                return {
                    "exists": False,
                    "needs_update": False,
                    "current_stage": None,
                    "reason": "Episode not in database",
                }

            # Check if stage needs updating
            current_stage = ProcessingStage(episode.processing_stage)
            target_stage = ProcessingStage.FORMATTED_TRANSCRIPT

            stage_order = list(ProcessingStage)
            current_index = stage_order.index(current_stage)
            target_index = stage_order.index(target_stage)

            needs_update = current_index < target_index

            return {
                "exists": True,
                "needs_update": needs_update,
                "current_stage": current_stage.value,
                "target_stage": target_stage.value,
                "reason": f"Stage {current_stage.value} -> {target_stage.value}"
                if needs_update
                else "Already at target stage",
            }
    except Exception as e:
        return {
            "exists": False,
            "needs_update": False,
            "current_stage": None,
            "reason": f"Database error: {e}",
        }


def dry_run_analysis(
    files: List[Path], output_dir: Path, force: bool, no_db_update: bool
) -> None:
    """
    Perform dry-run analysis showing what would be processed.

    Args:
        files: List of audio files to process
        output_dir: Output directory for transcripts
        force: Whether to force re-transcription
        no_db_update: Whether to skip database updates
    """
    print("=" * 80)
    print("DRY RUN - No files will be processed")
    print("=" * 80)
    print(f"\nOutput directory: {output_dir.absolute()}")
    print(f"Force re-transcription: {force}")
    print(f"Database updates: {'disabled' if no_db_update else 'enabled'}")
    print(f"\nFiles to process: {len(files)}")
    print("-" * 80)

    for idx, file_path in enumerate(files, 1):
        print(f"\n[{idx}/{len(files)}] {file_path.name}")
        print(f"  Path: {file_path.absolute()}")

        # Extract episode ID
        episode_id_str = get_episode_id_from_path(file_path)
        episode_id = int(episode_id_str)
        print(f"  Episode ID: {episode_id}")

        # Check cache status
        formatted_exists = check_formatted_transcript_exists(output_dir, episode_id)
        print(f"  Formatted transcript exists: {formatted_exists}")

        # Determine action
        if formatted_exists and not force:
            print(
                "  Action: SKIP (formatted transcript exists, use --force to re-process)"
            )
        else:
            if formatted_exists:
                print("  Action: RE-TRANSCRIBE (--force flag set)")
            else:
                print("  Action: TRANSCRIBE")

        # Check database status
        if not no_db_update:
            db_status = check_db_needs_update(episode_id, output_dir)
            if db_status["exists"]:
                print(
                    f"  Database: Episode exists (stage: {db_status['current_stage']})"
                )
                if db_status["needs_update"]:
                    print(f"  Database update: YES - {db_status['reason']}")
                else:
                    print(f"  Database update: NO - {db_status['reason']}")
            else:
                print(f"  Database: {db_status['reason']}")
        else:
            print("  Database update: DISABLED (--no-db-update flag)")

    print("\n" + "=" * 80)
    print("End of dry run")
    print("=" * 80)


def process_files(
    files: List[Path],
    output_dir: Path,
    language: str,
    force: bool,
    no_db_update: bool,
    logger: logging.Logger,
) -> Dict[str, List[str]]:
    """
    Process multiple audio files sequentially.

    Args:
        files: List of audio files to process
        output_dir: Output directory for transcripts
        language: Language code for transcription
        force: Force re-transcription even if formatted transcript exists
        no_db_update: Skip database updates
        logger: Logger instance

    Returns:
        Dict with 'success', 'skipped', and 'failed' lists of filenames
    """
    results = {"success": [], "skipped": [], "failed": []}

    print(f"\n{'=' * 80}")
    print(f"Processing {len(files)} file(s)")
    print(f"{'=' * 80}\n")

    for idx, file_path in enumerate(files, 1):
        print(f"[{idx}/{len(files)}] Processing: {file_path.name}")

        try:
            # Extract episode ID
            episode_id_str = get_episode_id_from_path(file_path)
            episode_id = int(episode_id_str)
            print(f"  Episode ID: {episode_id}")

            # Check if formatted transcript exists (unless force)
            formatted_exists = check_formatted_transcript_exists(output_dir, episode_id)

            if formatted_exists and not force:
                print("  ⊘ Skipped - formatted transcript already exists")
                print("    Use --force to re-transcribe")
                results["skipped"].append(file_path.name)

                # Still update DB if needed
                if not no_db_update:
                    db_status = check_db_needs_update(episode_id, output_dir)
                    if db_status["exists"] and db_status["needs_update"]:
                        print("  ↻ Updating database stage...")
                        try:
                            # Import here to avoid circular imports
                            from src.transcription.transcript import (
                                update_episode_transcription_paths,
                            )

                            # Build paths for DB update
                            ep_dir = output_dir / f"episode_{episode_id:03d}"
                            raw_path = ep_dir / f"raw_episode_{episode_id:03d}.json"
                            mapping_path = (
                                ep_dir / f"speakers_episode_{episode_id:03d}.json"
                            )
                            formatted_path = (
                                ep_dir / f"formatted_episode_{episode_id:03d}.txt"
                            )

                            update_episode_transcription_paths(
                                episode_id,
                                str(raw_path),
                                str(mapping_path),
                                str(formatted_path),
                            )
                            print("  ✓ Database updated")
                        except Exception as db_err:
                            print(f"  ✗ Database update failed: {db_err}")
                            logger.error(
                                f"DB update failed for episode {episode_id}: {db_err}"
                            )

                print()
                continue

            # Transcribe the file
            if formatted_exists:
                print("  ⟳ Re-transcribing (--force flag set)...")
            else:
                print("  ⟳ Transcribing...")

            # Temporarily modify transcribe_local_file to respect no_db_update
            # by catching the exception or checking the flag
            transcribe_local_file(
                input_file=file_path,
                language=language,
                output_dir=output_dir,
                episode_id=episode_id,
            )

            print("  ✓ Transcription completed successfully")
            results["success"].append(file_path.name)

        except FileNotFoundError as e:
            print(f"  ✗ Failed - file not found: {e}")
            logger.error(f"File not found: {file_path} - {e}")
            results["failed"].append(file_path.name)

        except Exception as e:
            print(f"  ✗ Failed - {e}")
            logger.error(f"Transcription failed for {file_path}: {e}")
            results["failed"].append(file_path.name)

        print()

    return results


def print_summary(results: Dict[str, List[str]]) -> None:
    """Print final summary of processing results."""
    print(f"\n{'=' * 80}")
    print("PROCESSING SUMMARY")
    print(f"{'=' * 80}")
    print(f"✓ Successful: {len(results['success'])}")
    print(f"⊘ Skipped: {len(results['skipped'])}")
    print(f"✗ Failed: {len(results['failed'])}")

    if results["failed"]:
        print("\nFailed files:")
        for filename in results["failed"]:
            print(f"  - {filename}")

    print(f"{'=' * 80}\n")


@log_function(logger_name="transcript", log_execution_time=True)
def update_episode_transcription_paths(
    episode_id: int,
    raw_transcript_path: str,
    speaker_mapping_path: str,
    formatted_transcript_path: str,
    transcript_duration: Optional[int] = None,
    transcript_confidence: Optional[float] = None,
) -> bool:
    """
    Update episode database record with transcription file paths.

    Args:
        episode_id: Database ID of the episode
        raw_transcript_path: Path to raw transcription JSON
        speaker_mapping_path: Path to speaker mapping JSON
        formatted_transcript_path: Path to formatted transcript text
        transcript_duration: Duration of the transcript audio in seconds
        transcript_confidence: Confidence score of the transcription

    Returns:
        bool: True if update successful, False otherwise
    """
    logger = logging.getLogger("audio_scraper")
    try:
        with get_db_session() as session:
            episode = session.query(Episode).filter_by(id=episode_id).first()

            if not episode:
                logger.error(f"Episode {episode_id} not found in database")
                return False

            # Update db fields
            stage_order = list(ProcessingStage)
            current_stage_index = stage_order.index(episode.processing_stage)
            target_stage_index = stage_order.index(ProcessingStage.FORMATTED_TRANSCRIPT)
            if current_stage_index < target_stage_index:
                episode.processing_stage = ProcessingStage.FORMATTED_TRANSCRIPT
            episode.raw_transcript_path = raw_transcript_path
            episode.speaker_mapping_path = speaker_mapping_path
            episode.formatted_transcript_path = formatted_transcript_path
            episode.transcript_duration = transcript_duration
            episode.transcript_confidence = transcript_confidence

            session.commit()
            logger.info(f"Updated episode ID {episode_id} with audio file path")
            return True
    except Exception as e:
        logger.error(f"Failed to update episode ID {episode_id}: {e}")
        return False


@log_function(logger_name="transcript", log_execution_time=True)
def transcribe_local_file(
    input_file: Union[str, Path],
    language: str = "fr",
    output_dir: Optional[Union[str, Path]] = "data/transcripts/",
    episode_id: Optional[int] = None,
):
    """High level function to transcribe a local audio file.

    Transcribe a local audio file and save the following files:
        - The raw transcription JSON with diarization
        - The speaker mapping JSON
        - The formatted transcript text file

    BEWARE: The files will be saved in a subdirectory of output_dir

    Transcribe using AssemblyAI Universal-2 with diarization.

    Args:
        input_path: Path to local audio file
        language: Language code for transcription (default: fr)
        output_dir: Directory to save output files (default: data/transcripts/)
        episode_id: Optional episode ID for naming else try to found it file name

    Raises:
        FileNotFoundError: If local file doesn't exist
        ValueError: If API key is missing
        Exception: If transcription or download fails
    """
    logger = logging.getLogger("transcript")

    try:
        # Find episode id for naming if not provided
        input_path = Path(input_file)
        episode_nbr = int(
            episode_id
            if episode_id is not None
            else get_episode_id_from_path(input_path)
        )

        # Create output directory if not exists
        out_dir_path = Path(output_dir / f"episode_{episode_nbr:03d}/")
        try:
            out_dir_path.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logger.error(f"Failed to create output directory {out_dir_path}: {e}")
            raise

        # Raw transcription
        raw_file_path = Path(out_dir_path / f"raw_episode_{episode_nbr:03d}.json")
        # Take transcription from cache if exists
        if raw_file_path.exists():
            raw_result = json.loads(raw_file_path.read_text(encoding="utf-8"))
        else:
            raw_result = transcribe_with_diarization(input_path, language)
            try:
                with open(raw_file_path, "w", encoding="utf-8") as f:
                    json.dump(raw_result, f, indent=4)
                    logger.info(f"Saved raw transcription to {raw_file_path}")
            except OSError as e:
                logger.error(f"Failed to write raw transcript to {raw_file_path}: {e}")
                raise

        # Speaker mapping
        mapping_file_path = Path(
            out_dir_path / f"speakers_episode_{episode_nbr:03d}.json"
        )
        # Take mapping from cache if exists
        mapping_result = {}
        if mapping_file_path.exists():
            raw_formatted_text = format_transcript(raw_file_path, max_tokens=10000)
        else:
            raw_formatted_text = format_transcript(raw_file_path, max_tokens=10000)
            mapping_result = map_speakers_with_llm(raw_formatted_text)
            try:
                with open(mapping_file_path, "w", encoding="utf-8") as f:
                    json.dump(mapping_result, f, indent=4)
                    logger.info(f"Saved mapping result to {mapping_file_path}")
            except OSError as e:
                logger.error(
                    f"Failed to write mapping result to {mapping_file_path}: {e}"
                )
                raise

        # Formatted transcript
        formatted_transcript_path = Path(
            out_dir_path / f"formatted_episode_{episode_nbr:03d}.txt"
        )
        formatted_text = format_transcript(
            raw_file_path, speaker_mapping=mapping_result
        )
        try:
            with open(formatted_transcript_path, "w", encoding="utf-8") as f:
                f.write(formatted_text)
                logger.info(f"Saved mapping result to {formatted_transcript_path}")
        except OSError as e:
            logger.error(
                f"Failed to write mapping result to {formatted_transcript_path}: {e}"
            )
            raise

        # Update database record
        try:
            transcript_duration = raw_result["transcript"].get("audio_duration")
            transcript_confidence = raw_result["transcript"].get("confidence")
            update_episode_transcription_paths(
                episode_nbr,
                str(raw_file_path),
                str(mapping_file_path),
                str(formatted_transcript_path),
                transcript_duration=transcript_duration,
                transcript_confidence=transcript_confidence,
            )
            logger.info("Database updated successfully")
        except Exception as db_error:
            logger.error(f"DB update failed but files saved: {db_error}")
            # Files exist but DB not updated - manual intervention needed
        # Return path to formatted transcript
        return formatted_transcript_path

    except Exception:
        raise


def main():
    """Main CLI function."""
    parser = argparse.ArgumentParser(
        description="Transcribe audio files using AssemblyAI with speaker diarization",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Single file
  uv run -m src.transcription data/audio/episode_001_title.mp3
  
  # Multiple files
  uv run -m src.transcription data/audio/episode_001.mp3 data/audio/episode_002.mp3
  
  # Custom output directory
  uv run -m src.transcription episode_001.mp3 -o custom/output/
  
  # Dry run (show what would be processed)
  uv run -m src.transcription episode_001.mp3 --dry-run
  
  # Force re-transcription
  uv run -m src.transcription episode_001.mp3 --force
  
  # Skip database updates
  uv run -m src.transcription episode_001.mp3 --no-db-update

Notes:
  - Episode IDs are extracted from filenames (pattern: episode_XXX_)
  - Skips transcription if formatted transcript already exists (use --force to override)
  - Processes multiple files sequentially, continuing on errors
  - Updates database by default (use --no-db-update to skip)
        """,
    )

    parser.add_argument(
        "files",
        nargs="+",
        type=Path,
        help="Audio file(s) to transcribe (supports multiple files)",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=Path("data/transcripts/"),
        help="Output directory for transcript files (default: data/transcripts/)",
    )
    parser.add_argument(
        "--language", default="fr", help="Language code for transcription (default: fr)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-transcription even if formatted transcript exists",
    )
    parser.add_argument(
        "--no-db-update",
        action="store_true",
        help="Skip database updates after transcription",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be processed without actually transcribing",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose logging output"
    )

    args = parser.parse_args()

    # Setup logging
    logger = setup_logging(
        logger_name="transcript", log_file="logs/transcript.log", verbose=args.verbose
    )

    # Validate input files
    valid_files = []
    for file_path in args.files:
        if not file_path.exists():
            print(f"✗ Error: File not found: {file_path}")
            logger.error(f"File not found: {file_path}")
            continue
        if not file_path.is_file():
            print(f"✗ Error: Not a file: {file_path}")
            logger.error(f"Not a file: {file_path}")
            continue
        valid_files.append(file_path)

    if not valid_files:
        print("✗ No valid files to process")
        sys.exit(1)

    # Dry run mode
    if args.dry_run:
        dry_run_analysis(valid_files, args.output_dir, args.force, args.no_db_update)
        sys.exit(0)

    # Process files
    logger.info(f"Starting transcription of {len(valid_files)} file(s)")

    try:
        results = process_files(
            files=valid_files,
            output_dir=args.output_dir,
            language=args.language,
            force=args.force,
            no_db_update=args.no_db_update,
            logger=logger,
        )

        # Print summary
        print_summary(results)

        # Exit with error code if any files failed
        if results["failed"]:
            logger.warning(
                f"Processing completed with {len(results['failed'])} failure(s)"
            )
            sys.exit(1)
        else:
            logger.info("All files processed successfully")
            sys.exit(0)

    except KeyboardInterrupt:
        print("\n\n✗ Interrupted by user")
        logger.info("Processing interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        logger.error(f"Unexpected error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
