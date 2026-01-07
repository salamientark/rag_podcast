"""
PostgreSQL database engine and session management for podcast RAG system.

This module provides PostgreSQL-specific database connectivity with:
- Session-per-operation pattern for backend scripts
- QueuePool connection pooling for optimal PostgreSQL performance
- Comprehensive error handling and file-based logging
- PostgreSQL optimization settings (connection pooling, timeouts, health checks)
"""

import os
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv
from contextlib import contextmanager
from typing import Generator, Any, Optional, Dict
from urllib.parse import urlparse

from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import SQLAlchemyError, OperationalError
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool

from .models import Base, Episode, ProcessingStage
from src.logger import setup_logging, log_function


# Initialize logger using centralized logging setup
db_logger = setup_logging(
    logger_name="database",
    log_file="logs/database.log",
    verbose=False,  # Only file logging, no console output
)


# Database configuration
env = load_dotenv(interpolate=True)
DATABASE_URL = os.getenv("BACKEND_URL")

if DATABASE_URL is None:
    db_logger.error("DATABASE_URL environment variable is not set")
    raise ValueError("DATABASE_URL environment variable is not set")


@log_function(
    logger_name="database", log_args=True, log_result=True, log_execution_time=True
)
def validate_database_url(url: str) -> tuple[bool, str]:
    """
    Validate that a string is a PostgreSQL connection URL and return a normalized connection string on success.

    Parameters:
        url (str): The database URL to validate.

    Returns:
        tuple[bool, str]: `True` and a normalized `postgresql://host:port/dbname` URL on success; `False` and an error message on failure.
    """
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("postgresql", "postgresql+psycopg2"):
            return (
                False,
                f"Only PostgreSQL databases are supported, got: {parsed.scheme}",
            )

        # Check required components
        if not parsed.hostname:
            return False, "Database hostname is missing"

        if not parsed.path or parsed.path == "/":
            return False, "Database name is missing"

        # Extract database name (remove leading /)
        db_name = parsed.path.lstrip("/")
        if not db_name:
            return False, "Database name is empty"

        return True, f"postgresql://{parsed.hostname}:{parsed.port or 5432}/{db_name}"

    except Exception as e:
        return False, f"Invalid database URL format: {e}"


def optimize_postgresql_connection(dbapi_connection, connection_record):
    """Apply PostgreSQL-specific optimizations when connection is created."""
    cursor = dbapi_connection.cursor()

    # Set connection-level optimizations
    cursor.execute("SET statement_timeout = '30s'")  # Query timeout
    cursor.execute(
        "SET idle_in_transaction_session_timeout = '60s'"
    )  # Idle transaction timeout
    cursor.execute("SET lock_timeout = '10s'")  # Lock timeout

    # Optimize for bulk operations
    cursor.execute("SET synchronous_commit = on")  # Ensure data durability
    cursor.execute("SET work_mem = '16MB'")  # Memory for sorting/hashing operations
    cursor.execute(
        "SET maintenance_work_mem = '64MB'"
    )  # Memory for maintenance operations

    # Connection pooling optimizations
    cursor.execute("SET tcp_keepalives_idle = 600")  # Keep alive settings
    cursor.execute("SET tcp_keepalives_interval = 30")
    cursor.execute("SET tcp_keepalives_count = 3")

    cursor.close()


# Validate database URL on module import
is_valid, db_info = validate_database_url(DATABASE_URL)
if not is_valid:
    db_logger.error(f"Database configuration error: {db_info}")
    raise ValueError(f"Database configuration error: {db_info}")

db_logger.info(f"Database configured: {db_info}")


# Create SQLAlchemy engine with QueuePool for PostgreSQL
try:
    engine = create_engine(
        DATABASE_URL,
        poolclass=QueuePool,
        pool_size=10,  # Optimal pool for PostgreSQL
        max_overflow=20,  # Allow burst connections
        pool_pre_ping=True,  # Health check connections
        pool_timeout=30,  # Connection wait timeout
        pool_recycle=3600,  # Recycle connections every hour
        echo=False,  # Set to True for SQL debugging
    )

    # Apply PostgreSQL optimizations on connection
    event.listen(engine, "connect", optimize_postgresql_connection)

    db_logger.info("Database engine created successfully")

except Exception as e:
    db_logger.error(f"Failed to create database engine: {e}")
    raise


# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """
    Provide a session-per-operation context manager that yields a SQLAlchemy Session.

    Yields a new Session for use within a with-statement, ensures rollback on errors, and always closes the session afterward. Creation, error conditions, and closure are logged.
    Returns:
        session (Session): A SQLAlchemy Session instance to use within the context.
    """
    session = SessionLocal()
    try:
        db_logger.debug("Database session created")
        yield session

    except OperationalError as e:
        db_logger.error(f"Database operational error: {e}")
        session.rollback()

        # Handle common PostgreSQL errors with helpful messages
        error_msg = str(e.orig) if hasattr(e, "orig") else str(e)
        if "connection" in error_msg.lower():
            db_logger.error(
                "Database connection failed. Please check if PostgreSQL is running and accessible."
            )
            raise
        elif "does not exist" in error_msg.lower():
            db_logger.error(
                "Database table does not exist. Please run database migrations first."
            )
            raise
        else:
            raise

    except SQLAlchemyError as e:
        db_logger.error(f"Database error: {e}")
        session.rollback()
        raise

    except Exception as e:
        db_logger.error(f"Unexpected database error: {e}")
        session.rollback()
        raise

    finally:
        session.close()
        db_logger.debug("Database session closed")


def fetch_db_episodes() -> list[Dict[str, Any]]:
    """Fetch all episodes from the database.

    Returns:
        List of Episode objects from the database, sorted by published date descending.
    """
    logger = logging.getLogger(__name__)
    logger.info("Fetching episodes from database...")
    dict_episodes = None
    with get_db_session() as session:
        episodes = session.query(Episode).order_by(Episode.published_date.desc()).all()
        dict_episodes = [episode.to_dict() for episode in episodes]
    logger.info(f"Fetched {len(episodes)} episodes from database.")
    return dict_episodes


def get_episode_from_date(
    date_start_str: str, days: Optional[int] = 1
) -> Optional[list[Dict[str, Any]]]:
    """Fetch an episode by published date range.

    Args:
        date_start_str (str): The published date of the episode in 'YYYY-MM-DD' format.
        days (int, optional): Number of days to include in the search range. Defaults to 1.

    Returns:
        Optional[list[Dict[str, Any]]]: The Episode dictionnaries if found, else None.
    """
    logger = logging.getLogger(__name__)
    logger.info(f"Fetching episode with published date: {date_start_str}")
    try:
        start = datetime.fromisoformat(date_start_str)
        end = start + timedelta(days=days)
    except ValueError as e:
        logger.error(f"Invalid date format: {e}")
        return None

    dict_episode = None
    with get_db_session() as session:
        episodes = (
            session.query(Episode)
            .filter(Episode.published_date >= start)
            .filter(Episode.published_date < end)
            .all()
        )
        if episodes:
            logger.info(f"Episodes found: {len(episodes)}")
            dict_episode = [episode.to_dict() for episode in episodes]
        else:
            logger.info("No episode found for the given date.")
    return dict_episode


@log_function(logger_name="database", log_execution_time=True)
def check_database_connection() -> bool:
    """
    Check if database connection is working.

    Returns:
        bool: True if connection is successful, False otherwise
    """
    try:
        with get_db_session() as session:
            # Simple query to test connection
            session.execute(text("SELECT 1"))
            db_logger.info("Database connection test successful")
            return True

    except Exception as e:
        db_logger.error(f"Database connection test failed: {e}")
        return False


@log_function(logger_name="database", log_execution_time=True)
def init_database() -> bool:
    """
    Initialize database by creating all tables defined in models.

    Note: This does not run Alembic migrations. Use alembic commands for migrations.

    Returns:
        bool: True if initialization successful, False otherwise
    """
    try:
        # Create all tables defined in Base.metadata
        Base.metadata.create_all(bind=engine)
        db_logger.info("Database tables created successfully")
        return True

    except Exception as e:
        db_logger.error(f"Failed to initialize database: {e}")
        return False


@log_function(logger_name="database", log_execution_time=True)
def get_database_info() -> dict:
    """
    Collects diagnostic information about the configured PostgreSQL database and the SQLAlchemy engine.

    Returns:
        dict: A mapping containing:
            - `database_url` (str): The configured DATABASE_URL.
            - `database_info` (str): Connection string information from validation.
            - `engine_pool_class` (str): Engine pool class name.
            - `pool_size` (int): Current pool size.
            - `pool_checked_in` (int): Number of checked-in connections.
            - `pool_checked_out` (int): Number of checked-out connections.
            - `pool_overflow` (int): Number of overflow connections.
        If an error occurs, returns a dict with an `error` key containing the error message.
    """
    try:
        info = {
            # "database_url": DATABASE_URL,
            "database_url": db_info,
            "engine_pool_class": engine.pool.__class__.__name__,
        }

        # Add PostgreSQL pool-specific info
        pool = engine.pool
        info.update(
            {
                "pool_size": pool.size(),
                "pool_checked_in": pool.checkedin(),
                "pool_checked_out": pool.checkedout(),
                "pool_overflow": pool.overflow(),
                "pool_status": "active",
            }
        )

        return info

    except Exception as e:
        db_logger.error(f"Failed to get database info: {e}")
        return {"error": str(e)}


@log_function(logger_name="database", log_execution_time=True)
def get_podcasts() -> list[str]:
    """
    Return a sorted list of unique podcast names stored in the database.

    Returns:
        list[str]: Alphabetically sorted list of podcast names. Returns an empty list if no podcasts are found or an error occurs while querying the database.
    """
    try:
        with get_db_session() as session:
            # Query distinct podcast names
            results = session.query(Episode.podcast).distinct().all()
            # Extract strings from tuples and sort
            podcasts = sorted([row[0] for row in results])
            db_logger.info(f"Retrieved {len(podcasts)} unique podcasts from database")
            return podcasts
    except Exception as e:
        db_logger.error(f"Failed to retrieve podcasts: {e}")
        return []


@log_function(logger_name="database", log_execution_time=True)
def update_episode_in_db(
    uuid: str,
    podcast: Optional[str] = None,
    episode_id: Optional[int] = None,
    title: Optional[str] = None,
    description: Optional[str] = None,
    published_date: Optional[datetime] = None,
    audio_url: Optional[str] = None,
    processing_stage: Optional[ProcessingStage] = None,
    audio_file_path: Optional[str] = None,
    raw_transcript_path: Optional[str] = None,
    speaker_mapping_path: Optional[str] = None,
    formatted_transcript_path: Optional[str] = None,
    transcript_duration: Optional[int] = None,
    transcript_confidence: Optional[float] = None,
):
    """
    Update an Episode record identified by UUID with any provided fields.

    Only parameters provided as non-None are written to the database; unspecified fields are left unchanged.

    Parameters:
        uuid: UUID of the episode to update.
        podcast: New podcast name (optional).
        episode_id: New episode identifier (optional).
        title: New episode title (optional).
        description: New episode description (optional).
        published_date: New published date/time (optional).
        audio_url: New audio file URL (optional).
        processing_stage: New processing stage enum value (optional).
        audio_file_path: Filesystem path to the stored audio file (optional).
        raw_transcript_path: Filesystem path to the raw transcript (optional).
        speaker_mapping_path: Filesystem path to the speaker mapping file (optional).
        formatted_transcript_path: Filesystem path to the formatted transcript (optional).
        transcript_duration: Transcript duration in seconds (optional).
        transcript_confidence: Transcript confidence score (optional).
    """
    try:
        # Create update dictionary
        update_data: dict[str, Any] = {}
        if podcast is not None:
            update_data["podcast"] = podcast
        if episode_id is not None:
            update_data["episode_id"] = episode_id
        if title is not None:
            update_data["title"] = title
        if description is not None:
            update_data["description"] = description
        if published_date is not None:
            update_data["published_date"] = published_date
        if audio_url is not None:
            update_data["audio_url"] = audio_url
        if processing_stage is not None:
            update_data["processing_stage"] = processing_stage
        if audio_file_path is not None:
            update_data["audio_file_path"] = audio_file_path
        if raw_transcript_path is not None:
            update_data["raw_transcript_path"] = raw_transcript_path
        if speaker_mapping_path is not None:
            update_data["speaker_mapping_path"] = speaker_mapping_path
        if formatted_transcript_path is not None:
            update_data["formatted_transcript_path"] = formatted_transcript_path
        if transcript_duration is not None:
            update_data["transcript_duration"] = transcript_duration
        if transcript_confidence is not None:
            update_data["transcript_confidence"] = transcript_confidence

        # Update the episode in the database
        with get_db_session() as session:
            if update_data:
                session.query(Episode).filter(Episode.uuid == uuid).update(
                    update_data, synchronize_session=False
                )
            session.commit()
    except Exception as e:
        raise e


# Log database configuration on module load
db_logger.info(f"Database module loaded. Configuration: {get_database_info()}")
