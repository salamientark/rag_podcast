#!/usr/bin/env python3
"""
Standalone script for embedding transcript files and storing in Qdrant vector database.

This module provides a command-line interface for batch processing transcript files,
generating embeddings using VoyageAI, and storing them in Qdrant collections with
optional local file storage.

Usage:
    uv run -m src.embedder.main file.txt
    uv run -m src.embedder.main file1.txt file2.txt file3.txt
    uv run -m src.embedder.main data/transcripts/**/*.txt
    uv run -m src.embedder.main *.txt --collection my_collection
    uv run -m src.embedder.main file.txt --dimensions 512 --save-local
    uv run -m src.embedder.main *.txt --dry-run --verbose

Examples:
    # Single file to default collection
    uv run -m src.embedder.main data/transcripts/episode_001/formatted_episode_001.txt

    # Multiple files with custom collection
    uv run -m src.embedder.main file1.txt file2.txt --collection podcasts

    # Glob pattern with custom dimensions and local save
    uv run -m src.embedder.main data/transcripts/**/*.txt --dimensions 512 --save-local

    # Dry run to validate files
    uv run -m src.embedder.main *.txt --dry-run --verbose

    # With explicit episode ID and podcast (both required together)
    uv run -m src.embedder.main transcript.txt --podcast my_podcast --episode-id 123

    # Process specific podcast's transcripts
    uv run -m src.embedder.main *.txt --podcast my_podcast
"""

import argparse
import sys
import glob as glob_module
import re
from pathlib import Path
from typing import Optional, Dict, Any
import logging

from src.embedder.embed import (
    embed_text,
    save_embedding_to_file,
    update_episode_processing_stage,
)
from src.transcription.transcript import get_episode_id_from_path
from src.db.qdrant_client import (
    get_qdrant_client,
    create_collection,
    insert_one_point,
    check_episode_exists_in_qdrant,
    QDRANT_COLLECTION_NAME,
    EMBEDDING_DIMENSION,
)
from src.db.database import (
    get_db_session,
    get_podcast_by_name_or_slug,
    get_all_podcasts,
)
from src.db.models import Episode
from src.logger import setup_logging


DEFAULT_EMBEDDING_OUTPUT_DIR = Path("data/embeddings")


def extract_episode_id_from_filename(file_path: Path) -> Optional[int]:
    """Extract episode ID from filename using multiple pattern matching strategies.

    Tries multiple patterns to extract episode numbers from filenames:
    - episode_NNN_ (with trailing underscore)
    - episode_NNN.txt (without trailing underscore)
    - episode_NNN/... (in directory path)

    Args:
        file_path: Path to the file.

    Returns:
        Optional[int]: Episode ID as integer, or None if not found.
    """
    path_str = str(file_path)

    # Try multiple patterns
    patterns = [
        r"episode[_-](\d{1,4})_",  # episode_672_ or episode-672_
        r"episode[_-](\d{1,4})\.",  # episode_672.txt or episode-672.json
        r"episode[_-](\d{1,4})/",  # episode_672/ in path
        r"episode[_-](\d{1,4})$",  # episode_672 at end
    ]

    for pattern in patterns:
        match = re.search(pattern, path_str)
        if match:
            episode_id = int(match.group(1))
            return episode_id

    # Fallback to original function (handles episode_NNN_ pattern)
    episode_str = get_episode_id_from_path(file_path)
    if episode_str and episode_str != "000":
        try:
            return int(episode_str)
        except ValueError:
            pass

    return None


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
        argparse.Namespace: Parsed command-line arguments.
    """
    parser = argparse.ArgumentParser(
        description="Embed transcript files and store in Qdrant vector database.",
        epilog="""
Examples:
  %(prog)s transcript.txt
  %(prog)s file1.txt file2.txt file3.txt
  %(prog)s data/transcripts/**/*.txt
  %(prog)s *.txt --collection my_collection --dimensions 512
  %(prog)s file.txt --save-local --verbose
  %(prog)s *.txt --dry-run
  %(prog)s *.txt --no-skip-existing  # Process all files, even if already embedded
  %(prog)s transcript.txt --podcast my_podcast --episode-id 123
  %(prog)s data/transcripts/**/*.txt --podcast my_podcast

For more information, see the embedder README.
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Required arguments
    parser.add_argument(
        "input_files",
        type=str,
        nargs="+",
        help="Path(s) to input transcript file(s). Supports glob patterns (e.g., *.txt, data/**/*.txt)",
    )

    # Optional arguments
    parser.add_argument(
        "--collection",
        type=str,
        default=QDRANT_COLLECTION_NAME,
        help=f"Qdrant collection name (default: {QDRANT_COLLECTION_NAME})",
    )

    parser.add_argument(
        "-d",
        "--dimensions",
        type=int,
        choices=[256, 512, 1024, 2048],
        default=EMBEDDING_DIMENSION,
        help=f"Output vector dimensions (default: {EMBEDDING_DIMENSION})",
    )

    parser.add_argument(
        "--save-local",
        action="store_true",
        help="Save embeddings as local .npy files in data/embeddings/ (format: episode_<id>_d<dim>.npy)",
    )

    parser.add_argument(
        "--episode-id",
        type=int,
        default=None,
        help="Episode ID for database tracking (default: auto-extract from filename)",
    )

    parser.add_argument(
        "--podcast",
        type=str,
        default=None,
        help="Podcast identifier for database tracking (required when --episode-id is provided)",
    )

    parser.add_argument(
        "--skip-existing",
        action="store_true",
        default=True,
        help="Skip transcripts already embedded in Qdrant collection (default: True)",
    )

    parser.add_argument(
        "--no-skip-existing",
        dest="skip_existing",
        action="store_false",
        help="Process all files even if already embedded (overrides default skip behavior)",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate files without processing (useful for testing)",
    )

    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging output",
    )

    args = parser.parse_args()

    # Validate --podcast and --episode-id dependency
    if args.episode_id is not None and args.podcast is None:
        parser.error("--podcast is required when --episode-id is provided")

    return args


def expand_glob_patterns(patterns: list[str]) -> list[Path]:
    """Expand glob patterns and convert to Path objects.

    Args:
        patterns (list[str]): List of file paths or glob patterns.

    Returns:
        list[Path]: List of resolved Path objects.
    """
    files = []
    for pattern in patterns:
        # Check if pattern contains glob wildcards
        if "*" in pattern or "?" in pattern or "[" in pattern:
            # Use glob to expand pattern
            matches = glob_module.glob(pattern, recursive=True)
            files.extend([Path(m) for m in matches])
        else:
            # Direct file path
            files.append(Path(pattern))

    # Remove duplicates while preserving order
    seen = set()
    unique_files = []
    for f in files:
        if f not in seen:
            seen.add(f)
            unique_files.append(f)

    return unique_files


def validate_files(
    files: list[Path], logger: logging.Logger
) -> tuple[list[Path], list[str]]:
    """Validate that files exist and are readable.

    Args:
        files (list[Path]): List of file paths to validate.
        logger (logging.Logger): Logger instance.

    Returns:
        tuple[list[Path], list[str]]: (valid_files, error_messages)
    """
    valid_files = []
    errors = []

    for file_path in files:
        if not file_path.exists():
            error_msg = f"File not found: {file_path}"
            logger.warning(error_msg)
            errors.append(error_msg)
            continue

        if not file_path.is_file():
            error_msg = f"Not a file: {file_path}"
            logger.warning(error_msg)
            errors.append(error_msg)
            continue

        if file_path.suffix not in [".txt", ".json"]:
            error_msg = f"Unsupported file type: {file_path} (expected .txt or .json)"
            logger.warning(error_msg)
            errors.append(error_msg)
            continue

        valid_files.append(file_path)

    return valid_files, errors


def get_episode_info_from_db(
    episode_id: int, podcast_id: Optional[int], logger: logging.Logger
) -> Optional[Dict[str, Any]]:
    """Fetch episode information from database.

    Args:
        episode_id (int): Episode number within podcast.
        podcast_id (Optional[int]): Podcast ID (FK) for filtering.
        logger (logging.Logger): Logger instance.

    Returns:
        Optional[Dict[str, Any]]: Episode info dict or None if not found.
    """
    try:
        with get_db_session() as session:
            query = session.query(Episode).filter_by(episode_id=episode_id)

            # Add podcast filter if provided
            if podcast_id:
                query = query.filter_by(podcast_id=podcast_id)

            episode = query.first()

            if episode:
                return {
                    "episode_id": episode.episode_id,
                    "title": episode.title,
                    "uuid": str(episode.uuid),
                }
            return None
    except Exception as e:
        logger.warning(f"Failed to fetch episode {episode_id} from database: {e}")
        return None


def process_single_file(
    file_path: Path,
    collection_name: str,
    dimensions: int,
    save_local: bool,
    episode_id: Optional[int],
    podcast_id: Optional[int],
    skip_existing: bool,
    logger: logging.Logger,
) -> Dict[str, Any]:
    """Process a single file: embed, store in Qdrant, optionally save locally.

    Args:
        file_path (Path): Path to transcript file.
        collection_name (str): Qdrant collection name.
        dimensions (int): Embedding dimensions.
        save_local (bool): Whether to save embeddings locally.
        episode_id (Optional[int]): Episode ID (if None, auto-extract from filename).
        podcast_id (Optional[int]): Podcast ID (FK) for filtering.
        skip_existing (bool): Whether to skip if episode already exists in Qdrant.
        logger (logging.Logger): Logger instance.

    Returns:
        Dict[str, Any]: Processing result with status and metadata.
            status: "success", "failed", or "skipped"

    Raises:
        Exception: If processing fails.
    """
    result = {
        "file": str(file_path),
        "status": "failed",
        "episode_id": None,
        "embedding_size": 0,
        "local_file": None,
        "error": None,
    }

    try:
        # Determine episode ID
        if episode_id is None:
            episode_id = extract_episode_id_from_filename(file_path)

        result["episode_id"] = episode_id
        logger.info(f"Processing {file_path.name} (episode_id={episode_id})")

        # Check if episode already exists in Qdrant
        if skip_existing and episode_id:
            with get_qdrant_client() as client:
                exists = check_episode_exists_in_qdrant(
                    client=client,
                    collection_name=collection_name,
                    episode_id=episode_id,
                )

            if exists:
                logger.info(
                    f"Skipping {file_path.name} - episode {episode_id} already exists in collection '{collection_name}'"
                )
                result["status"] = "skipped"
                return result

        # Load transcript text
        logger.debug(f"Loading transcript from: {file_path}")
        with file_path.open("r", encoding="utf-8") as f:
            transcript_text = f.read()

        if not transcript_text.strip():
            raise ValueError(f"Empty transcript file: {file_path}")

        # Generate embeddings
        logger.info(f"Generating {dimensions}D embeddings for {file_path.name}")
        embedding_result = embed_text(transcript_text, dimensions=dimensions)

        # Extract embeddings from result
        if hasattr(embedding_result, "embeddings"):
            embeddings = embedding_result.embeddings[0]  # Get first embedding
        else:
            embeddings = embedding_result

        result["embedding_size"] = len(embeddings)
        logger.debug(f"Generated embedding with {len(embeddings)} dimensions")

        # Fetch episode info from database for metadata
        episode_info = None
        if episode_id:
            episode_info = get_episode_info_from_db(episode_id, podcast_id, logger)

            # If both podcast_id and episode_id provided, episode MUST exist
            if podcast_id and episode_id and not episode_info:
                raise ValueError(
                    f"Episode {episode_id} not found for podcast_id={podcast_id}. "
                    "Cannot proceed without valid episode metadata."
                )

        # Create payload metadata
        payload = {
            "episode_id": episode_info["episode_id"] if episode_info else episode_id,
            "title": episode_info["title"] if episode_info else file_path.stem,
            "db_uuid": episode_info["uuid"] if episode_info else None,
            "source_file": str(file_path),
            "dimensions": dimensions,
        }

        # Insert into Qdrant
        logger.info(f"Storing embeddings in Qdrant collection '{collection_name}'")
        with get_qdrant_client() as client:
            insert_one_point(
                client=client,
                collection_name=collection_name,
                vector=embeddings,
                payload=payload,
            )
        logger.info(f"✓ Stored in Qdrant collection '{collection_name}'")

        # Optionally save to local file
        if save_local:
            # Format: episode_<id>_d<dimensions>.npy
            if episode_id:
                output_filename = f"episode_{episode_id:03d}_d{dimensions}.npy"
            else:
                output_filename = f"{file_path.stem}_d{dimensions}.npy"

            output_path = DEFAULT_EMBEDDING_OUTPUT_DIR / output_filename
            saved_path = save_embedding_to_file(output_path, embeddings)
            result["local_file"] = str(saved_path)
            logger.info(f"✓ Saved locally to: {saved_path}")

        # Update episode processing stage in database
        if episode_id:
            update_success = update_episode_processing_stage(str(episode_id))
            if update_success:
                logger.info(
                    f"✓ Updated episode {episode_id} processing stage to EMBEDDED"
                )

        result["status"] = "success"
        return result

    except Exception as e:
        logger.error(f"Failed to process {file_path}: {e}", exc_info=True)
        result["error"] = str(e)
        return result


def main() -> int:
    """Main entry point for the embedder batch processing CLI.

    Returns:
        int: Exit code (0 for success, 1 for error).
    """
    args = parse_arguments()

    # Setup logging
    logger = setup_logging(
        logger_name="embedder_main",
        log_file="logs/embedder_main.log",
        verbose=args.verbose,
    )

    try:
        logger.info("=" * 60)
        logger.info("Starting embedder batch processing")
        logger.info(f"Collection: {args.collection}")
        logger.info(f"Dimensions: {args.dimensions}")
        logger.info(f"Save local: {args.save_local}")
        logger.info(f"Skip existing: {args.skip_existing}")
        logger.info(f"Dry run: {args.dry_run}")
        logger.info(
            f"Episode ID: {args.episode_id if args.episode_id else 'auto-detect'}"
        )
        logger.info(f"Podcast: {args.podcast if args.podcast else 'N/A'}")
        logger.info("=" * 60)

        # Resolve podcast to get podcast_id if provided
        podcast_id = None
        if args.podcast:
            podcast = get_podcast_by_name_or_slug(args.podcast)
            if not podcast:
                available = ", ".join(p.slug for p in get_all_podcasts())
                logger.error(
                    f"Podcast '{args.podcast}' not found. Available: {available}"
                )
                return 1
            podcast_id = podcast.id
            logger.info(f"Resolved podcast '{args.podcast}' to id={podcast_id}")

        # Expand glob patterns
        print("Expanding file patterns...")
        files = expand_glob_patterns(args.input_files)
        logger.info(f"Found {len(files)} file(s) from patterns")

        if not files:
            print("Error: No files found matching the specified patterns")
            logger.error("No files found")
            return 1

        # Validate files
        print(f"Validating {len(files)} file(s)...")
        valid_files, errors = validate_files(files, logger)

        if errors:
            print(f"\nWarning: {len(errors)} file(s) failed validation:")
            for error in errors:
                print(f"  - {error}")

        if not valid_files:
            print("\nError: No valid files to process")
            logger.error("No valid files after validation")
            return 1

        print(f"✓ Found {len(valid_files)} valid file(s) to process")

        # Display file list
        if args.verbose or args.dry_run:
            print("\nFiles to process:")
            for i, f in enumerate(valid_files, 1):
                print(f"  {i}. {f}")

        # Dry run mode - exit after validation
        if args.dry_run:
            print("\n[DRY RUN] Validation complete. No files were processed.")
            logger.info("Dry run completed successfully")
            return 0

        # Create/verify Qdrant collection
        print(f"\nVerifying Qdrant collection '{args.collection}'...")
        with get_qdrant_client() as client:
            create_collection(
                client=client,
                name=args.collection,
                dimension=args.dimensions,
            )
        logger.info(f"Collection '{args.collection}' verified/created")
        print(f"✓ Collection '{args.collection}' ready")

        # Process files
        print(f"\nProcessing {len(valid_files)} file(s)...")
        print("-" * 60)

        results = []
        for i, file_path in enumerate(valid_files, 1):
            print(f"\n[{i}/{len(valid_files)}] Processing: {file_path.name}")

            try:
                result = process_single_file(
                    file_path=file_path,
                    collection_name=args.collection,
                    dimensions=args.dimensions,
                    save_local=args.save_local,
                    episode_id=args.episode_id,
                    podcast_id=podcast_id,
                    skip_existing=args.skip_existing,
                    logger=logger,
                )
                results.append(result)

                if result["status"] == "success":
                    print(f"  ✓ Successfully processed {file_path.name}")
                    if result.get("local_file"):
                        print(f"    Local file: {result['local_file']}")
                elif result["status"] == "skipped":
                    print("  ⊘ Skipped (already embedded)")
                else:
                    print(f"  ✗ Failed: {result.get('error', 'Unknown error')}")

            except Exception as e:
                logger.error(
                    f"Unexpected error processing {file_path}: {e}", exc_info=True
                )
                print(f"  ✗ Unexpected error: {e}")
                results.append(
                    {
                        "file": str(file_path),
                        "status": "failed",
                        "error": str(e),
                    }
                )

        # Summary
        print("\n" + "=" * 60)
        print("PROCESSING SUMMARY")
        print("=" * 60)

        successful = sum(1 for r in results if r["status"] == "success")
        skipped = sum(1 for r in results if r["status"] == "skipped")
        failed = sum(1 for r in results if r["status"] == "failed")

        print(f"Total files:    {len(results)}")
        print(f"Successful:     {successful}")
        print(f"Skipped:        {skipped} (already embedded)")
        print(f"Failed:         {failed}")
        print(f"Collection:     {args.collection}")
        print(f"Dimensions:     {args.dimensions}")

        if args.save_local:
            local_saved = sum(1 for r in results if r.get("local_file"))
            print(f"Saved locally:  {local_saved}")

        if failed > 0:
            print("\nFailed files:")
            for result in results:
                if result["status"] == "failed":
                    print(
                        f"  - {Path(result['file']).name}: {result.get('error', 'Unknown error')}"
                    )

        logger.info(
            f"Batch processing completed: {successful} successful, {skipped} skipped, {failed} failed"
        )
        print("\n✓ Batch processing complete!")

        return 0 if failed == 0 else 1

    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        logger.warning("Processing interrupted by user")
        return 130

    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        print(f"\nFatal error: {e}", file=sys.stderr)
        if args.verbose:
            import traceback

            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
