"""
Script to export a SQLite database table to a CSV file.

Usage:
    uv run scripts/sqlite_to_csv.py [--db DB_PATH] [--out CSV_PATH] [--table TABLE_NAME]
"""

import sqlite3
import csv
import argparse
import sys
import logging
from pathlib import Path
from typing import List

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("sqlite_to_csv")


def get_table_names(conn: sqlite3.Connection) -> List[str]:
    """Retrieve a list of all table names in the database."""
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    return [row[0] for row in cursor.fetchall()]


def export_table_to_csv(
    db_path: Path, csv_path: Path, table_name: str = "episodes"
) -> bool:
    """
    Export a SQLite table to a CSV file.

    Args:
        db_path: Path to the SQLite database file.
        csv_path: Path to the output CSV file.
        table_name: Name of the table to export.

    Returns:
        bool: True if export was successful, False otherwise.
    """
    if not db_path.exists():
        logger.error(f"Database file not found: {db_path}")
        return False

    try:
        # Connect to SQLite database
        logger.info(f"Connecting to database: {db_path}")
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()

            # Check if table exists
            tables = get_table_names(conn)
            if table_name not in tables:
                logger.error(
                    f"Table '{table_name}' not found. Available tables: {', '.join(tables)}"
                )
                return False

            # Fetch data
            logger.info(f"Reading data from table '{table_name}'...")
            cursor.execute(f"SELECT * FROM {table_name}")
            rows = cursor.fetchall()

            if not rows:
                logger.warning(f"Table '{table_name}' is empty.")
                # Still write headers if possible, or just exit
                # If no rows, cursor.description might still work if select was valid

            # Get column headers
            if cursor.description:
                headers = [description[0] for description in cursor.description]
            else:
                headers = []

            # Write to CSV
            logger.info(f"Writing {len(rows)} rows to {csv_path}...")

            # Ensure output directory exists
            csv_path.parent.mkdir(parents=True, exist_ok=True)

            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                if headers:
                    writer.writerow(headers)
                writer.writerows(rows)

        logger.info("Export completed successfully.")
        return True

    except sqlite3.Error as e:
        logger.error(f"SQLite error: {e}")
        return False
    except IOError as e:
        logger.error(f"File I/O error: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Export a SQLite database table to a CSV file.",
        epilog="Example: uv run scripts/sqlite_to_csv.py --db data/podcast.db --out data/episodes.csv",
    )

    parser.add_argument(
        "--db",
        type=Path,
        default=Path("data/podcast.db"),
        help="Path to the SQLite database file (default: data/podcast.db)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("data/episodes.csv"),
        help="Path to the output CSV file (default: data/episodes.csv)",
    )
    parser.add_argument(
        "--table",
        type=str,
        default="episodes",
        help="Name of the table to export (default: episodes)",
    )

    args = parser.parse_args()

    success = export_table_to_csv(args.db, args.out, args.table)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
