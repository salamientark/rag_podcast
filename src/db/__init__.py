"""
Database package for podcast RAG system.

This package contains all database-related functionality including:
- SQLAlchemy models and table definitions
- Database connection and session management
- Alembic migration support

Structure:
- models.py: SQLAlchemy ORM models (Episode, TimestampMixin)
- database.py: Database connection, engine, and session factory
- __init__.py: Package initialization and exports

All models inherit from a common Base declarative class and follow consistent
naming conventions (singular class names, plural table names).
"""

# Import key components for easy access
from .models import Base, Episode, ProcessingStage, TimestampMixin
from .database import (
    get_db_session,
    check_database_connection,
    init_database,
    get_database_info,
    engine,
    SessionLocal,
)

# This allows other parts of the application to import like:
# from src.db import Episode, Base, get_db_session
# instead of from src.db.models import Episode, Base

__all__ = [
    # Models
    "Base",
    "Episode",
    "ProcessingStage",
    "TimestampMixin",
    # Database utilities
    "get_db_session",
    "check_database_connection",
    "init_database",
    "get_database_info",
    "engine",
    "SessionLocal",
]
