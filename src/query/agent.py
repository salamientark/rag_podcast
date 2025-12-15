"""
Main query agent for the podcast RAG system.

This module provides the PodcastQueryAgent class that integrates:
- VoyageAI embeddings with existing Qdrant vectors
- LlamaIndex chat engine with memory
- Optional BGE-M3 reranking for French content
- Hidden metadata injection for rich LLM context
"""

import logging
from llama_index.core import VectorStoreIndex, Settings
from llama_index.core.memory import ChatMemoryBuffer
from llama_index.core.chat_engine import CondensePlusContextChatEngine
from llama_index.vector_stores.qdrant import QdrantVectorStore
from llama_index.llms.openai import OpenAI
from llama_index.embeddings.voyageai import VoyageEmbedding
from qdrant_client import QdrantClient, AsyncQdrantClient

from .config import QueryConfig, SYSTEM_PROMPT_FR
from .postprocessors import get_reranker


class PodcastQueryAgent:
    """
    Main query agent for podcast content using LlamaIndex and VoyageAI.

    Integrates with existing Qdrant vector store containing VoyageAI embeddings
    and provides a French chat interface with optional reranking.
    """

    def __init__(self, config: QueryConfig):
        """
        Initialize the podcast query agent.

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
            self._setup_chat_engine()
            self.logger.info("Podcast query agent initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize query agent: {e}")
            raise

    def _validate_config(self):
        """Validate required configuration and API keys"""
        if not self.config.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required")

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

        # OpenAI LLM
        Settings.llm = OpenAI(
            model=self.config.llm_model, api_key=self.config.openai_api_key
        )

        self.logger.info(
            f"Models configured: {self.config.llm_model} + {self.config.embedding_model}"
        )

    def _setup_vector_store(self):
        """Initialize Qdrant vector store connection"""
        try:
            # Use sync client for initial connection test
            sync_client = QdrantClient(url=self.config.qdrant_url)

            # Test connection by checking if collection exists
            collections = sync_client.get_collections()
            collection_names = [col.name for col in collections.collections]

            if self.config.collection_name not in collection_names:
                raise ConnectionError(
                    f"Collection '{self.config.collection_name}' not found. "
                    f"Available: {collection_names}"
                )

            # Create async client for vector store
            async_client = AsyncQdrantClient(url=self.config.qdrant_url)

            # Create vector store
            self.vector_store = QdrantVectorStore(
                aclient=async_client,
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

    def _setup_chat_engine(self):
        """Configure chat engine with postprocessors and memory"""
        # Build postprocessor pipeline (order matters!)
        postprocessors = []

        # 1. Optional reranking with BGE-M3 (French-optimized)
        if self.config.use_reranking:
            reranker = get_reranker(
                model_name=self.config.rerank_model, top_n=self.config.rerank_top_n
            )
            postprocessors.append(reranker)
            self.logger.info(f"Reranking enabled with {self.config.rerank_model}")
        else:
            self.logger.info("Reranking disabled (faster responses)")

        # Note: We'll handle metadata injection manually in the query method

        # Conversation memory
        memory = ChatMemoryBuffer.from_defaults(
            token_limit=self.config.memory_token_limit
        )

        # Create chat engine
        self.chat_engine = CondensePlusContextChatEngine.from_defaults(
            retriever=self.index.as_retriever(
                similarity_top_k=self.config.similarity_top_k
            ),
            node_postprocessors=postprocessors,
            memory=memory,
            system_prompt=SYSTEM_PROMPT_FR,
        )

        self.logger.info(
            f"Chat engine configured: top_k={self.config.similarity_top_k}, "
            f"memory={self.config.memory_token_limit} tokens"
        )

    async def query(self, message: str) -> str:
        """
        Process a user query and return a response.

        Args:
            message: User's question in French

        Returns:
            Agent's response in French

        Raises:
            Exception: If query processing fails
        """
        try:
            self.logger.debug(f"Processing query: {message[:50]}...")
            response = await self.chat_engine.achat(message)
            self.logger.debug(f"Generated response: {len(str(response))} characters")
            return str(response)

        except Exception as e:
            self.logger.error(f"Query processing failed: {e}")
            raise

    def get_status(self) -> dict:
        """
        Get agent status and configuration info.

        Returns:
            Dictionary with agent status information
        """
        return {
            "collection_name": self.config.collection_name,
            "qdrant_url": self.config.qdrant_url,
            "llm_model": self.config.llm_model,
            "embedding_model": self.config.embedding_model,
            "reranking_enabled": self.config.use_reranking,
            "rerank_model": self.config.rerank_model
            if self.config.use_reranking
            else None,
            "memory_limit": self.config.memory_token_limit,
        }
