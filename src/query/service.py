"""
Core podcast query service - stateless RAG processing.

This module provides the PodcastQueryService class that handles:
- VoyageAI embeddings with existing Qdrant vectors
- LlamaIndex retrieval and generation
- Optional BGE-M3 reranking for French content
- Stateless single-shot queries (no conversation memory)
"""

import logging
from typing import Optional
from llama_index.core import VectorStoreIndex, Settings
from llama_index.core.retrievers import VectorIndexRetriever
from llama_index.core.query_engine import RetrieverQueryEngine
from llama_index.vector_stores.qdrant import QdrantVectorStore
from llama_index.llms.anthropic import Anthropic
from llama_index.embeddings.voyageai import VoyageEmbedding
from qdrant_client import QdrantClient, AsyncQdrantClient

from .config import QueryConfig
from .postprocessors import sort_nodes_temporally


class PodcastQueryService:
    """
    Core stateless RAG service for podcast content.

    Handles vector retrieval and LLM generation without conversation memory.
    Designed to be wrapped by conversational or stateless interfaces.
    """

    def __init__(self, config: QueryConfig):
        """
        Initialize the core query service.

        Args:
            config: QueryConfig instance with all settings

        Raises:
            ConnectionError: If unable to connect to Qdrant
            ValueError: If API keys are missing
        """
        self.config = config
        self.logger = logging.getLogger(__name__)

        try:
            self._validate_config()
            self._setup_models()
            self._setup_vector_store()
            self._setup_query_engine()
            self.logger.info("Podcast query service initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize query service: {e}")
            raise

    def _validate_config(self):
        """Validate required configuration and API keys"""
        if not self.config.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY is required")

        if not self.config.voyage_api_key:
            raise ValueError("VOYAGE_API_KEY is required")

    def _setup_models(self):
        """Configure LLM and embedding models"""
        # VoyageAI embeddings (compatible with existing vectors)
        Settings.embed_model = VoyageEmbedding(
            voyage_api_key=self.config.voyage_api_key,
            model_name=self.config.embedding_model,
            output_dimension=self.config.embedding_dimensions,
        )

        # Anthropic Claude LLM
        Settings.llm = Anthropic(
            model=self.config.llm_model, api_key=self.config.anthropic_api_key
        )

        self.logger.info(
            f"Models configured: {self.config.llm_model} + {self.config.embedding_model}"
        )

    def _setup_vector_store(self):
        """Initialize Qdrant vector store connection"""
        try:
            # Use sync client for initial connection test
            sync_client = QdrantClient(
                url=self.config.qdrant_url, api_key=self.config.qdrant_api_key
            )

            # Test connection by checking if collection exists
            collections = sync_client.get_collections()
            collection_names = [col.name for col in collections.collections]

            if self.config.collection_name not in collection_names:
                raise ConnectionError(
                    f"Collection '{self.config.collection_name}' not found. "
                    f"Available: {collection_names}"
                )

            # Create async client for vector store
            async_client = AsyncQdrantClient(
                url=self.config.qdrant_url, api_key=self.config.qdrant_api_key
            )

            # Create vector store with both sync and async clients
            self.vector_store = QdrantVectorStore(
                client=sync_client,  # Sync client for query operations
                aclient=async_client,  # Async client for async operations
                collection_name=self.config.collection_name,
            )

            # Create index from existing vectors
            self.index = VectorStoreIndex.from_vector_store(self.vector_store)

            self.logger.info(
                f"Connected to Qdrant collection: {self.config.collection_name}"
            )

        except Exception as e:
            self.logger.error(f"Failed to connect to Qdrant: {e}")
            raise ConnectionError(
                f"Cannot connect to Qdrant at {self.config.qdrant_url}: {e}"
            )

    def _setup_query_engine(self):
        """Configure stateless query engine with postprocessors"""
        # Build postprocessor pipeline (order matters!)
        postprocessors = []

        # Reranker would go here, removed for now to reduce image size
        # See get_reranker() in postprocessors.py if re-enabling

        # Create retriever
        self.retriever = VectorIndexRetriever(
            index=self.index,
            similarity_top_k=self.config.similarity_top_k,
        )

        # Store postprocessors for temporal sorting
        self.postprocessors = postprocessors

        # Create stateless query engine (no memory)
        self.query_engine = RetrieverQueryEngine.from_args(
            retriever=self.retriever,
            node_postprocessors=postprocessors,
            # Note: No system prompt here - will be handled by wrappers
        )

        self.logger.info(
            f"Query engine configured: top_k={self.config.similarity_top_k}"
        )

    async def query(self, question: str, context: Optional[str] = None) -> str:
        """
        Process a single query without conversation memory.

        Args:
            question: User's question in French
            context: Optional context from external conversation management

        Returns:
            Generated response in French

        Raises:
            Exception: If query processing fails
        """
        try:
            self.logger.debug(f"Processing query: {question[:50]}...")

            # If context is provided, combine it with the question
            if context:
                enhanced_question = f"Context: {context}\n\nQuestion: {question}"
            else:
                enhanced_question = question

            # First retrieve nodes
            retrieved_nodes = await self.retriever.aretrieve(enhanced_question)

            # Apply temporal sorting if needed
            sorted_nodes = sort_nodes_temporally(retrieved_nodes, enhanced_question)

            # Apply postprocessors
            if hasattr(self, "postprocessors") and self.postprocessors:
                for postprocessor in self.postprocessors:
                    if hasattr(postprocessor, "postprocess_nodes"):
                        sorted_nodes = postprocessor.postprocess_nodes(sorted_nodes)

            # Generate response using sorted nodes with the LLM from Settings
            from llama_index.core.response_synthesizers import ResponseMode
            from llama_index.core import get_response_synthesizer

            synthesizer = get_response_synthesizer(
                response_mode=ResponseMode.COMPACT, llm=Settings.llm
            )

            response = await synthesizer.asynthesize(enhanced_question, sorted_nodes)
            self.logger.debug(f"Generated response: {len(str(response))} characters")
            return str(response)

        except Exception as e:
            self.logger.error(f"Query processing failed: {e}")
            # Fallback to original method if temporal sorting fails
            try:
                if context:
                    enhanced_question = f"Context: {context}\n\nQuestion: {question}"
                else:
                    enhanced_question = question
                response = await self.query_engine.aquery(enhanced_question)
                return str(response)
            except Exception:
                raise e

    def get_status(self) -> dict:
        """
        Get service status and configuration info.

        Returns:
            Dictionary with service status information
        """
        return {
            "service_type": "stateless",
            "collection_name": self.config.collection_name,
            "qdrant_url": self.config.qdrant_url,
            "llm_model": self.config.llm_model,
            "embedding_model": self.config.embedding_model,
            "reranking_enabled": False,
            "similarity_top_k": self.config.similarity_top_k,
        }
