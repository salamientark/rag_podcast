#!/usr/bin/env python3
"""CLI for generating embeddings from transcript files.

This module provides a command-line interface for embedding transcript text
using VoyageAI's embedding models with configurable dimensions.

Usage:
    uv run -m src.embedder input_file.json
    uv run -m src.embedder input_file.json --dimensions 512
    uv run -m src.embedder input_file.json -d 2048 -o custom_output.npy
    uv run -m src.embedder input_file.json --verbose

Examples:
    # Basic usage with default settings (1024 dimensions)
    uv run -m src.embedder data/transcript/episode_672_universal.json

    # With custom dimensions
    uv run -m src.embedder episode.json --dimensions 256

    # With custom output path
    uv run -m src.embedder episode.json -o embeddings/my_episode.npy

    # With verbose logging
    uv run -m src.embedder episode.json --verbose
"""

import argparse
import sys
from pathlib import Path

from src.embedder.embed import embed_text, save_embedding_to_file
from src.transcription import get_mapped_transcript
from src.logger import setup_logging


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
        argparse.Namespace: Parsed command-line arguments.
    """
    parser = argparse.ArgumentParser(
        description="Generate embeddings from transcript files using VoyageAI.",
        epilog="""
Examples:
  %(prog)s data/transcript/episode_672.json
  %(prog)s episode.json --dimensions 512
  %(prog)s episode.json -d 2048 -o embeddings/output.npy
  %(prog)s episode.json --verbose
  
For more information, see the embedder README.
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Required arguments
    parser.add_argument(
        "input_file",
        type=Path,
        help="Path to the input transcript TXT file",
    )

    # Optional arguments
    parser.add_argument(
        "-d",
        "--dimensions",
        type=int,
        choices=[256, 512, 1024, 2048],
        default=1024,
        help="Output vector dimensions (default: 1024)",
    )

    parser.add_argument(
        "-o",
        "--outfile",
        type=Path,
        default=None,
        help="Output file path (default: data/embeddings/<input_filename>.npy)",
    )

    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging output",
    )

    return parser.parse_args()


def generate_default_output_path(input_file: Path) -> Path:
    """Generate default output path from input filename.

    Args:
        input_file (Path): Input transcript file path.

    Returns:
        Path: Default output path in data/embeddings/ directory.
    """
    # Remove all extensions and use base name
    base_name = input_file.stem
    return Path("data/embeddings") / f"{base_name}.npy"


def validate_input_file(input_file: Path) -> None:
    """Validate that the input file exists and is readable.

    Args:
        input_file (Path): Path to the input file.

    Raises:
        FileNotFoundError: If input file doesn't exist.
        ValueError: If input file is not a JSON file.
    """
    if not input_file.exists():
        raise FileNotFoundError(f"Input file not found: {input_file}")

    if not input_file.is_file():
        raise ValueError(f"Input path is not a file: {input_file}")


def main() -> int:
    """Main entry point for the embedder CLI.

    Returns:
        int: Exit code (0 for success, 1 for error).
    """
    args = parse_arguments()

    # Setup logging
    logger = setup_logging(
        logger_name="embedder",
        log_file="logs/embedder.log",
        verbose=args.verbose,
    )

    try:
        # Validate input file
        logger.info(f"Validating input file: {args.input_file}")
        validate_input_file(args.input_file)

        # Determine output path
        output_path = (
            args.outfile
            if args.outfile
            else generate_default_output_path(args.input_file)
        )
        logger.info(f"Output will be saved to: {output_path}")

        # Load and process transcript
        logger.info(f"Loading transcript from: {args.input_file}")
        print(f"Loading transcript from {args.input_file}...")
        # raw_transcript = get_mapped_transcript(args.input_file)
        with open(args.input_file, "r", encoding="utf-8") as f:
            transcript = f.read()


        if args.verbose:
            print(f"Transcript preview (first 500 chars):\n{transcript[:500]}\n")

        # Generate embeddings
        logger.info(f"Generating embeddings with {args.dimensions} dimensions")
        print(f"Generating embeddings with {args.dimensions} dimensions...")
        embedding_result = embed_text(transcript, dimensions=args.dimensions)

        # Extract embeddings from result
        # VoyageAI returns a result object with .embeddings attribute (list of lists)
        if hasattr(embedding_result, "embeddings"):
            embeddings = embedding_result.embeddings[
                0
            ]  # Get first embedding for single text
        else:
            embeddings = embedding_result

        if args.verbose:
            if hasattr(embedding_result, "total_tokens"):
                print(f"Total tokens processed: {embedding_result.total_tokens}")
            print(f"Embedding shape: {len(embeddings)} dimensions")

        # Save to file
        logger.info(f"Saving embeddings to: {output_path}")
        print(f"Saving embeddings to {output_path}...")
        saved_path = save_embedding_to_file(output_path, embeddings)

        print(f"✓ Successfully saved embeddings to: {saved_path}")
        logger.info("Embedding generation completed successfully")

        return 0

    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        print(f"Error: {e}", file=sys.stderr)
        return 1

    except ValueError as e:
        logger.error(f"Validation error: {e}")
        print(f"Error: {e}", file=sys.stderr)
        return 1

    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        print(f"Error: An unexpected error occurred: {e}", file=sys.stderr)
        if args.verbose:
            import traceback

            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
