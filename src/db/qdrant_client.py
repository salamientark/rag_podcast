"""
Qdrant vector database client for podcast RAG system.

Provides context-managed connections to Qdrant vector store with:
- Connection pooling and automatic cleanup
- Error handling and logging
- Collection management utilities
- VoyageAI embedding support (1024 dimensions)

Usage:
    from src.db.qdrant_client import get_qdrant_client, create_collection

    # Create a collection
    with get_qdrant_client() as client:
        create_collection(client, "my_collection")

    # Check connection
    if check_qdrant_connection():
        print("Qdrant is ready!")
"""

import uuid
import os
from contextlib import contextmanager
from typing import Generator, Dict, Any

from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance

from src.logger import setup_logging, log_function


# Configuration
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_COLLECTION_NAME = os.getenv("QDRANT_COLLECTION_NAME", "podcast_embeddings")
EMBEDDING_DIMENSION = 1024  # VoyageAI voyage-3.5 embedding dimension


# Setup logger
qdrant_logger = setup_logging(
    logger_name="qdrant_client",
    log_file="logs/qdrant_client.log",
    verbose=False,
)


@contextmanager
def get_qdrant_client() -> Generator[QdrantClient, None, None]:
    """
    Context manager for Qdrant client connections.

    Provides automatic connection cleanup and error handling.
    Suitable for RAG operations and vector storage.

    Usage:
        with get_qdrant_client() as client:
            collections = client.get_collections()
            client.upsert(collection_name="...", points=[...])

    Yields:
        QdrantClient: An active Qdrant client instance

    Raises:
        Exception: If connection to Qdrant server fails
    """
    client = None
    try:
        qdrant_logger.debug(f"Connecting to Qdrant at {QDRANT_URL}")
        client = QdrantClient(url=QDRANT_URL)
        qdrant_logger.debug("Qdrant client connection established")
        yield client

    except Exception as e:
        qdrant_logger.error(f"Qdrant client error: {e}")
        raise

    finally:
        if client is not None:
            client.close()
            qdrant_logger.debug("Qdrant client connection closed")


@log_function(logger_name="qdrant_client", log_execution_time=True)
def check_qdrant_connection() -> bool:
    """
    Check if Qdrant connection is working.

    Returns:
        bool: True if connection is successful, False otherwise
    """
    try:
        with get_qdrant_client() as client:
            # Simple health check
            client.get_collections()
            qdrant_logger.info("Qdrant connection test successful")
            return True

    except Exception as e:
        qdrant_logger.error(f"Qdrant connection test failed: {e}")
        return False


@log_function(logger_name="qdrant_client", log_execution_time=True)
def get_qdrant_info() -> Dict[str, Any]:
    """
    Get information about the Qdrant server and collections.

    Returns:
        dict: Qdrant server information including collections, version, etc.
    """
    try:
        with get_qdrant_client() as client:
            collections = client.get_collections()

            info = {
                "qdrant_url": QDRANT_URL,
                "default_collection": QDRANT_COLLECTION_NAME,
                "embedding_dimension": EMBEDDING_DIMENSION,
                "collections": [col.name for col in collections.collections],
                "collection_count": len(collections.collections),
            }

            return info

    except Exception as e:
        qdrant_logger.error(f"Failed to get Qdrant info: {e}")
        return {"error": str(e)}


@log_function(logger_name="qdrant_client", log_execution_time=True)
def create_collection(
    client: QdrantClient,
    name: str,
    dimension: int = EMBEDDING_DIMENSION,
    distance: Distance = Distance.COSINE,
) -> None:
    """
    Create a Qdrant collection if it does not exist.

    Args:
        client (QdrantClient): Active Qdrant client instance
        name (str): Name of the collection to create
        dimension (int): Vector dimension size (default: 1024 for VoyageAI)
        distance (Distance): Distance metric for similarity (default: COSINE)

    Raises:
        Exception: If collection creation fails
    """
    if not client.collection_exists(collection_name=name):
        qdrant_logger.info(
            f"Creating Qdrant collection: {name} (dimension={dimension})"
        )
        client.create_collection(
            collection_name=name,
            vectors_config=VectorParams(size=dimension, distance=distance),
        )
        qdrant_logger.info(f"Collection '{name}' created successfully")
    else:
        qdrant_logger.debug(f"Collection '{name}' already exists")


@log_function(logger_name="qdrant_client", log_execution_time=True)
def insert_one_point(
    client: QdrantClient,
    collection_name: str,
    vector: list[float],
    payload: Dict[str, Any] = None,
) -> None:
    """Insert a single vector into the specified Qdrant collection.
    id is auto-generated.

    Args:
        client (QdrantClient): Active Qdrant client instance
        collection_name (str): Name of the collection to insert into
        vector (list[float]): The embedding vector to insert
        payload (Dict[str, Any], optional): Additional metadata to store with the vector
    """
    vector_id = str(uuid.uuid4())
    client.upsert(
        collection_name=collection_name,
        points=[
            {
                "id": vector_id,
                "vector": vector,
                "payload": payload or {},
            }
        ],
    )


# Log Qdrant configuration on module load
qdrant_logger.info(
    f"Qdrant module loaded. URL: {QDRANT_URL}, "
    f"Default collection: {QDRANT_COLLECTION_NAME}, "
    f"Embedding dimension: {EMBEDDING_DIMENSION}"
)


if __name__ == "__main__":
    # Test Qdrant client with context manager
    print(f"Testing Qdrant connection to {QDRANT_URL}...")

    if check_qdrant_connection():
        print("✓ Connection successful!")

        # Get server info
        info = get_qdrant_info()
        print("\nQdrant Info:")
        print(f"  Collections: {info.get('collections', [])}")
        print(f"  Total: {info.get('collection_count', 0)}")

        # Test collection creation
        test_collection = "test_collection"
        print(f"\nCreating collection '{test_collection}'...")
        with get_qdrant_client() as client:
            create_collection(client, test_collection)
        print(f"✓ Collection '{test_collection}' ready!")

    else:
        print("✗ Connection failed!")
        print("\nMake sure Qdrant is running:")
        print(
            "  docker run -p 6333:6333 -v $(pwd)/qdrant_storage:/qdrant/storage qdrant/qdrant"
        )
