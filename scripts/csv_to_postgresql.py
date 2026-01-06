"""CSV to PostgreSQL importer.

Imports rows from a CSV file into the configured PostgreSQL database using the
project's SQLAlchemy models.

Usage:
    uv run scripts/csv_to_postgresql.py --csv data/episodes.csv

Notes:
    - Requires `DATABASE_URL` to be configured (see `.env.example`).
    - Default mode is upsert: rows are inserted or updated by `uuid`.
"""

from __future__ import annotations

import argparse
import csv
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy.exc import SQLAlchemyError

import sys

sys.path.insert(1, str(Path(__file__).resolve().parent.parent))

from src.db.database import get_db_session
from src.db.models import Episode, ProcessingStage

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ImportStats:
    """Counters tracked during CSV import."""

    processed: int = 0
    inserted_or_updated: int = 0
    skipped: int = 0


def _parse_optional_int(value: str | None) -> int | None:
    """
    Parse an optional integer from a string, returning None for empty or missing input.
    
    Parameters:
        value (str | None): A string containing an integer, or None/whitespace to indicate absence.
    
    Returns:
        int | None: The parsed integer, or `None` if `value` is `None` or contains only whitespace.
    
    Raises:
        ValueError: If `value` is non-empty but cannot be parsed as an integer.
    """
    if value is None:
        return None

    stripped = value.strip()
    if not stripped:
        return None

    return int(stripped)


def _parse_optional_float(value: str | None) -> float | None:
    """
    Convert a string containing a floating-point number to a float or return None for empty input.
    
    Parameters:
        value (str | None): String to parse; may be None or contain only whitespace.
    
    Returns:
        float | None: The parsed float when `value` contains a numeric representation, `None` if `value` is `None` or empty after trimming.
    """
    if value is None:
        return None

    stripped = value.strip()
    if not stripped:
        return None

    return float(stripped)


def _parse_optional_datetime(value: str | None) -> datetime | None:
    """
    Parse a string into a datetime using multiple common formats.
    
    Parameters:
        value (str | None): Input string to parse. If `None` or empty/whitespace, returns `None`.
    
    Returns:
        datetime | None: A `datetime` object when parsing succeeds, or `None` for empty input.
    
    Raises:
        ValueError: If the input is non-empty and does not match ISO format or any of the accepted patterns ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S").
    """
    if value is None:
        return None

    stripped = value.strip()
    if not stripped:
        return None

    try:
        return datetime.fromisoformat(stripped)
    except ValueError:
        pass

    for fmt in (
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
    ):
        try:
            return datetime.strptime(stripped, fmt)
        except ValueError:
            continue

    raise ValueError(f"Unsupported datetime format: {stripped}")


def _parse_processing_stage(
    value: str | None, *, coerce_unknown: bool
) -> ProcessingStage | None:
    """
    Convert a string to a ProcessingStage enum value, accepting case-insensitive and whitespace-padded input.
    
    Parameters:
    	value: The input string to parse; leading/trailing whitespace is ignored. If `None` or empty after trimming, the function returns `None`.
    	coerce_unknown: If `True`, unknown values are mapped to `ProcessingStage.SYNCED` with a warning; if `False`, unknown values raise `ValueError`.
    
    Returns:
    	A `ProcessingStage` corresponding to the input string, or `None` when `value` is `None` or empty.
    
    Raises:
    	ValueError: If the trimmed value does not match any `ProcessingStage` member and `coerce_unknown` is `False`.
    """
    if value is None:
        return None

    stripped = value.strip().lower()
    if not stripped:
        return None

    try:
        return ProcessingStage(stripped)
    except ValueError:
        if coerce_unknown:
            logger.warning(
                "Unknown processing_stage '%s'; coercing to 'synced'", stripped
            )
            return ProcessingStage.SYNCED
        raise


def _episode_kwargs_from_row(
    row: dict[str, str],
    *,
    coerce_unknown_stage: bool,
) -> dict[str, Any]:
    """
    Builds a dictionary of keyword arguments for an Episode from a CSV row, validating required fields and converting optional string values to their parsed Python types.
    
    Parameters:
        row (dict[str, str]): Mapping of CSV header names to string values for a single row.
        coerce_unknown_stage (bool): If True, unknown processing stage values are coerced to a default stage instead of causing an error.
    
    Returns:
        dict[str, Any]: Parsed and trimmed values suitable for constructing an Episode (includes required keys: `uuid`, `episode_id`, `title`, `podcast`, `published_date`, `audio_url`; optional keys include `description`, `processing_stage`, file path fields, `transcript_duration`, `transcript_confidence`, `created_at`, `updated_at`).
    
    Raises:
        ValueError: If a required field is missing or if a field has an invalid format (for example, an unparsable datetime or missing numeric `episode_id`).
    """
    uuid = (row.get("uuid") or "").strip()
    if not uuid:
        raise ValueError("Missing required field: uuid")

    required_int = _parse_optional_int(row.get("episode_id"))
    if required_int is None:
        raise ValueError("Missing required field: episode_id")

    title = (row.get("title") or "").strip()
    if not title:
        raise ValueError("Missing required field: title")

    podcast = (row.get("podcast") or "").strip()
    if not podcast:
        raise ValueError("Missing required field: podcast")

    published_date = _parse_optional_datetime(row.get("published_date"))
    if published_date is None:
        raise ValueError("Missing required field: published_date")

    audio_url = (row.get("audio_url") or "").strip()
    if not audio_url:
        raise ValueError("Missing required field: audio_url")

    kwargs: dict[str, Any] = {
        "uuid": uuid,
        "episode_id": required_int,
        "podcast": podcast,
        "title": title,
        "published_date": published_date,
        "audio_url": audio_url,
    }

    description = row.get("description")
    if description is not None:
        description_stripped = description.strip()
        kwargs["description"] = description_stripped if description_stripped else None

    stage = _parse_processing_stage(
        row.get("processing_stage"), coerce_unknown=coerce_unknown_stage
    )
    if stage is not None:
        kwargs["processing_stage"] = stage

    for optional_field in (
        "audio_file_path",
        "raw_transcript_path",
        "speaker_mapping_path",
        "formatted_transcript_path",
    ):
        value = row.get(optional_field)
        if value is None:
            continue
        stripped = value.strip()
        kwargs[optional_field] = stripped if stripped else None

    duration = _parse_optional_int(row.get("transcript_duration"))
    if duration is not None:
        kwargs["transcript_duration"] = duration

    confidence = _parse_optional_float(row.get("transcript_confidence"))
    if confidence is not None:
        kwargs["transcript_confidence"] = confidence

    created_at = _parse_optional_datetime(row.get("created_at"))
    if created_at is not None:
        kwargs["created_at"] = created_at

    updated_at = _parse_optional_datetime(row.get("updated_at"))
    if updated_at is not None:
        kwargs["updated_at"] = updated_at

    return kwargs


def import_csv_to_postgresql(
    csv_path: Path,
    *,
    delimiter: str,
    batch_size: int,
    dry_run: bool,
    fail_fast: bool,
    coerce_unknown_stage: bool,
) -> ImportStats:
    """
    Import rows from a CSV file into PostgreSQL by upserting Episode records in batches.
    
    Processes the CSV at `csv_path`, parses each row into Episode fields, and performs upserts (via session.merge). Commits every `batch_size` upserts (or flushes and rolls back when `dry_run` is True). If `fail_fast` is True any parsing or database error will be re-raised; otherwise the row is counted as skipped and processing continues. When `coerce_unknown_stage` is True unknown processing stages are coerced to a default value instead of raising.
    
    Parameters:
        csv_path (Path): Path to the CSV file to import.
        delimiter (str): Field delimiter used by the CSV reader.
        batch_size (int): Number of upserts between commits.
        dry_run (bool): If True, perform database operations but roll back instead of committing.
        fail_fast (bool): If True, raise on the first parse or database error; otherwise continue and count skipped rows.
        coerce_unknown_stage (bool): If True, coerce unrecognized processing stage values instead of raising.
    
    Returns:
        ImportStats: Counts of processed rows, inserted_or_updated rows, and skipped rows.
    
    Raises:
        FileNotFoundError: If `csv_path` does not exist.
        ValueError: If the CSV is missing header row.
    """

    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    with csv_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter=delimiter)
        if reader.fieldnames is None:
            raise ValueError("CSV appears to be missing headers")

        with get_db_session() as session:
            processed = 0
            upserted = 0
            skipped = 0

            for row_index, row in enumerate(reader, start=2):
                processed += 1
                try:
                    kwargs = _episode_kwargs_from_row(
                        row, coerce_unknown_stage=coerce_unknown_stage
                    )
                except Exception as exc:
                    skipped += 1
                    logger.error(
                        "Row %s skipped due to parse error: %s", row_index, exc
                    )
                    if fail_fast:
                        raise
                    continue

                try:
                    session.merge(Episode(**kwargs))
                    upserted += 1
                except SQLAlchemyError as exc:
                    skipped += 1
                    logger.error(
                        "Row %s skipped due to database error: %s", row_index, exc
                    )
                    if fail_fast:
                        raise
                    session.rollback()
                    session.expire_all()
                    continue

                if upserted % batch_size == 0:
                    if dry_run:
                        session.flush()
                        session.rollback()
                    else:
                        session.commit()
                    logger.info("Imported %s rows...", upserted)

            if dry_run:
                session.flush()
                session.rollback()
            else:
                session.commit()

    return ImportStats(
        processed=processed, inserted_or_updated=upserted, skipped=skipped
    )


def _build_parser() -> argparse.ArgumentParser:
    """
    Builds and returns an argparse.ArgumentParser configured for the CSV-to-PostgreSQL importer CLI.
    
    The parser defines arguments for the CSV path, delimiter, batch size, dry-run mode, fail-fast behavior,
    coercing unknown processing stages, and log level, and includes usage examples in the epilog.
    
    Returns:
        argparse.ArgumentParser: Parser configured with the importer command-line options.
    """
    parser = argparse.ArgumentParser(
        description="Import Episode rows from a CSV file into PostgreSQL.",
        epilog=(
            "Examples:\n"
            "  uv run scripts/csv_to_postgresql.py --csv data/episodes.csv\n"
            "  uv run scripts/csv_to_postgresql.py --csv data/episodes.csv --dry-run\n"
            "  uv run scripts/csv_to_postgresql.py --csv data/episodes.csv --batch-size 500"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--csv",
        type=Path,
        required=True,
        help="Path to the input CSV file.",
    )
    parser.add_argument(
        "--delimiter",
        type=str,
        default=",",
        help="CSV delimiter character (default: ',').",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=1000,
        help="Commit every N rows (default: 1000).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and validate CSV, but do not persist changes.",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop on first row error instead of continuing.",
    )
    parser.add_argument(
        "--coerce-unknown-stage",
        action="store_true",
        help="Coerce unknown `processing_stage` values to 'synced'.",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity (default: INFO).",
    )

    return parser


def main() -> None:
    """
    Parse command-line arguments, configure logging, run the CSV-to-PostgreSQL import process, and log final processed/imported/skipped counts.
    """
    parser = _build_parser()
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    stats = import_csv_to_postgresql(
        args.csv,
        delimiter=args.delimiter,
        batch_size=args.batch_size,
        dry_run=args.dry_run,
        fail_fast=args.fail_fast,
        coerce_unknown_stage=args.coerce_unknown_stage,
    )

    logger.info(
        "Done. processed=%s imported=%s skipped=%s",
        stats.processed,
        stats.inserted_or_updated,
        stats.skipped,
    )


if __name__ == "__main__":
    main()