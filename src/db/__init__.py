"""
Database package for podcast RAG system.

This package contains all database-related functionality including:
- SQLAlchemy models and table definitions
- Database connection and session management
- Alembic migration support

Structure:
- models.py: SQLAlchemy ORM models (Episode, TimestampMixin)
- database.py: Database connection, engine, and session factory
- qdrant_client.py: Qdrant vector database client and utilities
- __init__.py: Package initialization and exports

Database Patterns:
- SQLite uses session-per-operation with get_db_session() context manager
- Qdrant uses connection-per-operation with get_qdrant_client() context manager

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
    get_podcasts,
    engine,
    SessionLocal,
    update_episode_in_db,
)
from .qdrant_client import (
    get_qdrant_client,
    check_qdrant_connection,
    get_qdrant_info,
    insert_one_point,
    create_collection,
    QDRANT_URL,
    QDRANT_COLLECTION_NAME,
    EMBEDDING_DIMENSION,
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
    "get_podcasts",
    "engine",
    "SessionLocal",
    "update_episode_in_db",
    # Qdrant Vector Database utilities
    "get_qdrant_client",
    "check_qdrant_connection",
    "get_qdrant_info",
    "create_collection",
    "insert_one_point",
    "QDRANT_URL",
    "QDRANT_COLLECTION_NAME",
    "EMBEDDING_DIMENSION",
]
