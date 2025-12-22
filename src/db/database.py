"""
SQLite database engine and session management for podcast RAG system.

This module provides SQLite-specific database connectivity with:
- Session-per-operation pattern for backend scripts
- NullPool connection pooling to avoid SQLite locking issues
- Comprehensive error handling and file-based logging
- SQLite optimization settings (WAL mode, foreign keys, timeouts)
"""

import os
from dotenv import load_dotenv
from contextlib import contextmanager
from pathlib import Path
from typing import Generator
from urllib.parse import urlparse

from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import SQLAlchemyError, OperationalError
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import NullPool

from .models import Base
from src.logger import setup_logging, log_function


# Initialize logger using centralized logging setup
db_logger = setup_logging(
    logger_name="database",
    log_file="logs/database.log",
    verbose=False,  # Only file logging, no console output
)


# Database configuration
env = load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")


@log_function(
    logger_name="database", log_args=True, log_result=True, log_execution_time=True
)
def validate_database_url(url: str) -> tuple[bool, str]:
    """Validate the database URL format and path."""
    try:
        parsed = urlparse(url)
        if parsed.scheme != "sqlite":
            return False, f"Only SQLite databases are supported, got: {parsed.scheme}"

        # Extract database file path (remove leading /)
        db_path = parsed.path.lstrip("/")
        if not db_path:
            return False, "Database file path is empty"

        # Check if parent directory exists (but don't create it)
        parent_dir = Path(db_path).parent
        if not parent_dir.exists():
            return False, f"Database directory does not exist: {parent_dir}"

        return True, db_path

    except Exception as e:
        return False, f"Invalid database URL format: {e}"


def optimize_sqlite_connection(dbapi_connection, connection_record):
    """Apply SQLite-specific optimizations when connection is created."""
    cursor = dbapi_connection.cursor()

    # Enable WAL mode for better concurrent access
    cursor.execute("PRAGMA journal_mode=WAL")

    # Set busy timeout to 30 seconds to handle locks
    cursor.execute("PRAGMA busy_timeout=30000")

    # Enable foreign key constraints
    cursor.execute("PRAGMA foreign_keys=ON")

    # Optimize for better performance
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA cache_size=1000")
    cursor.execute("PRAGMA temp_store=MEMORY")

    cursor.close()


# Validate database URL on module import
is_valid, db_info = validate_database_url(DATABASE_URL)
if not is_valid:
    db_logger.error(f"Database configuration error: {db_info}")
    raise ValueError(f"Database configuration error: {db_info}")

db_logger.info(f"Database configured: {db_info}")


# Create SQLAlchemy engine with NullPool for SQLite
try:
    engine = create_engine(
        DATABASE_URL,
        poolclass=NullPool,  # Avoid connection pooling issues with SQLite
        echo=False,  # Set to True to log SQL queries
        connect_args={
            "check_same_thread": False,  # Allow multi-threading
            "timeout": 30,  # Connection timeout in seconds
        },
    )

    # Apply SQLite optimizations on connection
    event.listen(engine, "connect", optimize_sqlite_connection)

    db_logger.info("Database engine created successfully")

except Exception as e:
    db_logger.error(f"Failed to create database engine: {e}")
    raise


# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """
    Context manager for database sessions (session-per-operation pattern).

    Provides automatic session cleanup, error handling, and logging.
    Suitable for backend scripts and batch operations.

    Usage:
        with get_db_session() as session:
            episode = Episode(title="Test", guid="123")
            session.add(episode)
            session.commit()
    """
    session = SessionLocal()
    try:
        db_logger.debug("Database session created")
        yield session

    except OperationalError as e:
        db_logger.error(f"Database operational error: {e}")
        session.rollback()

        # Handle common SQLite errors with helpful messages
        error_msg = str(e.orig) if hasattr(e, "orig") else str(e)
        if "database is locked" in error_msg.lower():
            raise OperationalError(
                "Database is locked. This may be due to another process accessing the database. "
                "Please try again or check for long-running database operations.",
                None,
                None,
            )
        elif "no such table" in error_msg.lower():
            raise OperationalError(
                "Database table does not exist. Please run database migrations first.",
                None,
                None,
            )
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
    Get information about the database.

    Returns:
        dict: Database information including file size, path, etc.
    """
    try:
        info = {
            "database_url": DATABASE_URL,
            "database_path": db_info,
            "engine_pool_class": engine.pool.__class__.__name__,
        }

        # Add file-specific info for SQLite
        if os.path.exists(db_info):
            file_stats = os.stat(db_info)
            info.update(
                {
                    "file_exists": True,
                    "file_size_bytes": file_stats.st_size,
                    "file_size_mb": round(file_stats.st_size / (1024 * 1024), 2),
                    "last_modified": file_stats.st_mtime,
                }
            )
        else:
            info["file_exists"] = False

        return info

    except Exception as e:
        db_logger.error(f"Failed to get database info: {e}")
        return {"error": str(e)}


# Log database configuration on module load
db_logger.info(f"Database module loaded. Configuration: {get_database_info()}")
