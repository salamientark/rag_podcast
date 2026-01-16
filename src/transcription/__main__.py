#!/usr/bin/env python3
"""
CLI interface for transcription using Gemini with speaker identification.

Usage:
    uv run -m src.transcription --podcast "Podcast Name" <file1.mp3> [file2.mp3 ...]
    uv run -m src.transcription --podcast "Podcast Name" <file1.mp3> -o data/transcripts/
    uv run -m src.transcription --podcast "Podcast Name" <file1.mp3> --dry-run

Examples:
    # Single file with default output
    uv run -m src.transcription --podcast "Podcast Name" data/audio/episode_001_title.mp3

    # Multiple files
    uv run -m src.transcription --podcast "Podcast Name" data/audio/episode_001.mp3 data/audio/episode_002.mp3

    # Dry run to check what would be processed
    uv run -m src.transcription --podcast "Podcast Name" episode_*.mp3 --dry-run

    # Force re-transcription even if transcript exists
    uv run -m src.transcription --podcast "Podcast Name" episode_001.mp3 --force
"""

import sys
import argparse
import re
from pathlib import Path
from typing import List, Dict
import logging

from src.transcription.gemini_transcript import transcribe_with_gemini
from src.logger import setup_logging
from src.db.database import get_db_session
from src.db.models import Episode, ProcessingStage


def get_episode_id_from_path(file_path: Path) -> int:
    """Extract episode number from file path.

    Args:
        file_path: Path to audio file

    Returns:
        Episode ID as int, or 0 if not found
    """
    pattern = re.compile(r"episode_(\d{3})")
    match = pattern.search(str(file_path))
    if match:
        return int(match.group(1))
    return 0


def get_episode_from_db(podcast_name: str, episode_id: int) -> dict | None:
    """Get episode data from database.

    Args:
        podcast_name: Podcast name
        episode_id: Episode ID number

    Returns:
        Episode dict with uuid and description, or None if not found
    """
    try:
        with get_db_session() as session:
            episode = (
                session.query(Episode)
                .filter(
                    Episode.podcast.ilike(podcast_name),
                    Episode.episode_id == episode_id,
                )
                .first()
            )
            if episode:
                return {
                    "uuid": episode.uuid,
                    "description": episode.description or "",
                }
    except Exception:
        pass
    return None


def update_episode_transcript_path(uuid: str, transcript_path: str) -> bool:
    """Update episode with transcript path in database.

    Args:
        uuid: Episode UUID
        transcript_path: Path to formatted transcript

    Returns:
        True if successful, False otherwise
    """
    try:
        with get_db_session() as session:
            episode = session.query(Episode).filter(Episode.uuid == uuid).first()
            if episode:
                episode.formatted_transcript_path = transcript_path
                episode.processing_stage = ProcessingStage.FORMATTED_TRANSCRIPT
                session.commit()
                return True
    except Exception:
        pass
    return False


def process_files(
    files: List[Path],
    output_dir: Path,
    podcast_name: str,
    force: bool,
    no_db_update: bool,
    logger: logging.Logger,
) -> Dict[str, List[str]]:
    """Process multiple audio files.

    Args:
        files: List of audio files to process
        output_dir: Output directory for transcripts
        podcast_name: Podcast name
        force: Force re-transcription
        no_db_update: Skip database updates
        logger: Logger instance

    Returns:
        Dict with 'success', 'skipped', and 'failed' lists
    """
    results = {"success": [], "skipped": [], "failed": []}

    print(f"\n{'=' * 60}")
    print(f"Processing {len(files)} file(s)")
    print(f"{'=' * 60}\n")

    for idx, file_path in enumerate(files, 1):
        print(f"[{idx}/{len(files)}] Processing: {file_path.name}")

        try:
            episode_id = get_episode_id_from_path(file_path)
            print(f"  Episode ID: {episode_id}")

            # Get episode from database for description
            episode_data = get_episode_from_db(podcast_name, episode_id)
            description = episode_data["description"] if episode_data else ""

            # Check if transcript exists
            ep_dir = output_dir / f"episode_{episode_id:03d}"
            transcript_path = ep_dir / f"formatted_episode_{episode_id:03d}.txt"

            if transcript_path.exists() and not force:
                print(
                    "  Skipped - transcript already exists (use --force to re-process)"
                )
                results["skipped"].append(file_path.name)
                continue

            # Create output directory
            ep_dir.mkdir(parents=True, exist_ok=True)

            # Transcribe
            print("  Transcribing with Gemini...")
            result = transcribe_with_gemini(file_path, description)

            # Save transcript
            transcript_path.write_text(result["formatted_text"], encoding="utf-8")
            print(f"  Saved transcript to {transcript_path}")

            # Update database
            if not no_db_update and episode_data:
                if update_episode_transcript_path(
                    episode_data["uuid"], str(transcript_path)
                ):
                    print("  Database updated")
                else:
                    print("  Database update failed")

            results["success"].append(file_path.name)
            print("  Done")

        except FileNotFoundError as e:
            print(f"  Failed - file not found: {e}")
            logger.error(f"File not found: {file_path} - {e}")
            results["failed"].append(file_path.name)

        except Exception as e:
            print(f"  Failed - {e}")
            logger.error(f"Transcription failed for {file_path}: {e}")
            results["failed"].append(file_path.name)

        print()

    return results


def dry_run_analysis(
    files: List[Path],
    output_dir: Path,
    podcast_name: str,
    force: bool,
) -> None:
    """Show what would be processed without doing it."""
    print("=" * 60)
    print("DRY RUN - No files will be processed")
    print("=" * 60)
    print(f"\nOutput directory: {output_dir.absolute()}")
    print(f"Podcast: {podcast_name}")
    print(f"Force: {force}")
    print(f"\nFiles: {len(files)}")
    print("-" * 60)

    for idx, file_path in enumerate(files, 1):
        print(f"\n[{idx}] {file_path.name}")
        episode_id = get_episode_id_from_path(file_path)
        print(f"  Episode ID: {episode_id}")

        transcript_path = (
            output_dir
            / f"episode_{episode_id:03d}"
            / f"formatted_episode_{episode_id:03d}.txt"
        )
        exists = transcript_path.exists()
        print(f"  Transcript exists: {exists}")

        if exists and not force:
            print("  Action: SKIP")
        else:
            print("  Action: TRANSCRIBE")

    print("\n" + "=" * 60)


def main():
    """Main CLI function."""
    parser = argparse.ArgumentParser(
        description="Transcribe audio files using Gemini with speaker identification",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "files",
        nargs="+",
        type=Path,
        help="Audio file(s) to transcribe",
    )
    parser.add_argument(
        "--podcast",
        type=str,
        required=True,
        help="Podcast name (for database lookup)",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=Path("data/transcripts/"),
        help="Output directory (default: data/transcripts/)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-transcription even if transcript exists",
    )
    parser.add_argument(
        "--no-db-update",
        action="store_true",
        help="Skip database updates",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be processed without doing it",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    # Setup logging
    logger = setup_logging(
        logger_name="transcript",
        log_file="logs/transcript.log",
        verbose=args.verbose,
    )

    # Validate files
    valid_files = []
    for file_path in args.files:
        if not file_path.exists():
            print(f"Error: File not found: {file_path}")
            continue
        if not file_path.is_file():
            print(f"Error: Not a file: {file_path}")
            continue
        valid_files.append(file_path)

    if not valid_files:
        print("No valid files to process")
        sys.exit(1)

    # Dry run
    if args.dry_run:
        dry_run_analysis(valid_files, args.output_dir, args.podcast, args.force)
        sys.exit(0)

    # Process files
    logger.info(f"Starting transcription of {len(valid_files)} file(s)")

    try:
        results = process_files(
            files=valid_files,
            output_dir=args.output_dir,
            podcast_name=args.podcast,
            force=args.force,
            no_db_update=args.no_db_update,
            logger=logger,
        )

        # Summary
        print(f"{'=' * 60}")
        print("SUMMARY")
        print(f"{'=' * 60}")
        print(f"Success: {len(results['success'])}")
        print(f"Skipped: {len(results['skipped'])}")
        print(f"Failed: {len(results['failed'])}")

        if results["failed"]:
            print("\nFailed files:")
            for f in results["failed"]:
                print(f"  - {f}")
            sys.exit(1)

    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        logger.error(f"Unexpected error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
