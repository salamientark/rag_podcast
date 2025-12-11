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
from dotenv import load_dotenv
from contextlib import contextmanager
from typing import Generator, Dict, Any, Optional

from qdrant_client import QdrantClient
from qdrant_client.models import (
    VectorParams,
    Distance,
    Filter,
    FieldCondition,
    MatchValue,
)

from src.logger import setup_logging, log_function


# Configuration
load_dotenv()
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_COLLECTION_NAME = os.getenv("QDRANT_COLLECTION_NAME")
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


@log_function(logger_name="qdrant_client", log_execution_time=True)
def check_episode_exists_in_qdrant(
    client: QdrantClient,
    collection_name: str,
    episode_id: int,
) -> bool:
    """Check if an episode is already embedded in the Qdrant collection.

    Queries the collection for any points with matching episode_id in payload.

    Args:
        client (QdrantClient): Active Qdrant client instance
        collection_name (str): Name of the collection to search
        episode_id (int): Episode ID to check for

    Returns:
        bool: True if episode exists in collection, False otherwise
    """
    try:
        # Check if collection exists first
        if not client.collection_exists(collection_name=collection_name):
            qdrant_logger.debug(
                f"Collection '{collection_name}' does not exist, episode not found"
            )
            return False

        # Build filter for episode_id
        scroll_filter = Filter(
            must=[FieldCondition(key="episode_id", match=MatchValue(value=episode_id))]
        )

        # Query for matching points (limit 1 since we only need to know if it exists)
        records, _ = client.scroll(
            collection_name=collection_name,
            scroll_filter=scroll_filter,
            limit=1,
            with_payload=True,
            with_vectors=False,
        )

        exists = len(records) > 0
        if exists:
            qdrant_logger.debug(
                f"Episode {episode_id} found in collection '{collection_name}'"
            )
        else:
            qdrant_logger.debug(
                f"Episode {episode_id} not found in collection '{collection_name}'"
            )

        return exists

    except Exception as e:
        qdrant_logger.error(
            f"Error checking if episode {episode_id} exists in '{collection_name}': {e}"
        )
        # On error, return False to allow processing (fail-open approach)
        return False


@log_function(logger_name="qdrant_client", log_execution_time=True)
def get_episode_vectors(
    client: QdrantClient,
    collection_name: str,
    episode_id: int,
) -> Optional[list[list[float]]]:
    """
    Retrieve all embedding vectors for an episode from Qdrant.

    Handles both legacy single-chunk episodes and new multi-chunk episodes.

    Args:
        client (QdrantClient): Active Qdrant client instance
        collection_name (str): Name of the collection to search
        episode_id (int): Episode ID to retrieve

    Returns:
        List of embedding vectors (sorted by chunk_index), or None if not found
    """
    try:
        # Check if collection exists first
        if not client.collection_exists(collection_name=collection_name):
            qdrant_logger.debug(
                f"Collection '{collection_name}' does not exist, cannot retrieve vector"
            )
            return None

        # Build filter for episode_id
        scroll_filter = Filter(
            must=[FieldCondition(key="episode_id", match=MatchValue(value=episode_id))]
        )

        # Query for ALL matching points (not just limit=1)
        records, _ = client.scroll(
            collection_name=collection_name,
            scroll_filter=scroll_filter,
            limit=100,  # Assume max 100 chunks per episode
            with_payload=True,
            with_vectors=True,
        )

        if len(records) == 0:
            qdrant_logger.debug(
                f"Episode {episode_id} not found in collection '{collection_name}'"
            )
            return None

        # Sort by chunk_index if present (for multi-chunk episodes)
        # For legacy episodes without chunk_index, treat as single chunk
        records_sorted = sorted(records, key=lambda r: r.payload.get("chunk_index", 0))

        # Extract vectors - handle both list and dict formats
        vectors = []
        for record in records_sorted:
            vector = record.vector
            # If vector is dict (named vectors), get the default vector
            if isinstance(vector, dict):
                vector = vector.get("", list(vector.values())[0] if vector else [])
            vectors.append(vector)

        qdrant_logger.info(
            f"Retrieved {len(vectors)} chunk vector(s) for episode {episode_id}"
        )
        return vectors

    except Exception as e:
        qdrant_logger.error(
            f"Error retrieving vectors for episode {episode_id} from '{collection_name}': {e}"
        )
        return None


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
