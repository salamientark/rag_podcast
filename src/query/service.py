"""
Core podcast query service - stateless RAG processing.

This module provides the PodcastQueryService class that handles:
- VoyageAI embeddings with existing Qdrant vectors
- LlamaIndex retrieval and generation
- Optional BGE-M3 reranking for French content
- Stateless single-shot queries (no conversation memory)
"""

import contextlib
import logging
from typing import Optional

from llama_index.core import Settings, VectorStoreIndex, get_response_synthesizer
from llama_index.core.query_engine import RetrieverQueryEngine
from llama_index.core.retrievers import VectorIndexRetriever
from llama_index.core.vector_stores.types import MetadataFilter, MetadataFilters
from llama_index.core.response_synthesizers import ResponseMode
from llama_index.embeddings.voyageai import VoyageEmbedding
from llama_index.llms.anthropic import Anthropic
from llama_index.vector_stores.qdrant import QdrantVectorStore
from qdrant_client import AsyncQdrantClient, QdrantClient

from src.observability.langfuse import get_langfuse

from .config import QueryConfig
from .postprocessors import sort_nodes_temporally


SNIPPET_SIZE = 500  # Characters for Langfuse node preview


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
        """Validate required configuration and API keys.

        Raises:
            ValueError: If required API keys are missing.
        """
        if not self.config.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY is required")

        if not self.config.voyage_api_key:
            raise ValueError("VOYAGE_API_KEY is required")

    def _setup_models(self):
        """Configure LLM and embedding models.

        Sets global LlamaIndex `Settings` for the embed model and LLM.

        Raises:
            Exception: If model initialization fails.
        """
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
        """Initialize the Qdrant vector store and LlamaIndex index.

        Connects to Qdrant, validates the configured collection exists, and builds
        a `VectorStoreIndex` backed by the existing vectors.

        Raises:
            ConnectionError: If Qdrant is unreachable or the collection is missing.
        """
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
        """Configure the stateless retriever and query engine.

        Builds a `VectorIndexRetriever` and a `RetrieverQueryEngine` without any
        conversation memory. Node postprocessors are stored for optional manual
        postprocessing in `query()`.
        """
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

    async def _retrieve_nodes(
        self,
        retriever,
        langfuse,
        enhanced_question,
        podcast_filter_applied: bool,
        normalized_podcast: Optional[str],
    ):
        """Retrieve candidate nodes for a question.

        Wraps `retriever.aretrieve` and (when available) records retrieval details in
        Langfuse, including a short text snippet preview and key node metadata.

        Args:
            retriever: LlamaIndex retriever to use (optionally filtered).
            langfuse: Langfuse client used for tracing spans.
            enhanced_question: Question string (possibly augmented with context).
            podcast_filter_applied: Whether a podcast metadata filter is used.
            normalized_podcast: Normalized podcast name used in the filter.

        Returns:
            Retrieved nodes when tracing succeeds; otherwise returns `None`.
        """
        try:
            retrieve_cm = langfuse.start_as_current_observation(
                as_type="span",
                name="rag.retrieve",
            )
        except Exception as exc:
            self.logger.debug(f"Langfuse retrieve span start failed: {exc}")
            retrieve_cm = contextlib.nullcontext()
        with retrieve_cm as retrieve_span:
            retrieved_nodes = await retriever.aretrieve(enhanced_question)

            if retrieve_span is not None:
                try:
                    retrieved_previews = []
                    for node_with_score in retrieved_nodes:
                        metadata = getattr(node_with_score.node, "metadata", {}) or {}
                        try:
                            raw_text = node_with_score.node.get_content()
                        except Exception:
                            raw_text = ""

                        snippet = " ".join(str(raw_text).split())[:SNIPPET_SIZE]
                        retrieved_previews.append(
                            {
                                "score": node_with_score.score,
                                "podcast": metadata.get("podcast"),
                                "episode_id": metadata.get("episode_id"),
                                "title": metadata.get("title"),
                                "publication_date": metadata.get("publication_date"),
                                "chunk_index": metadata.get("chunk_index"),
                                "snippet": snippet,
                            }
                        )

                    retrieve_span.update(
                        output={
                            "num_nodes": len(retrieved_nodes),
                            "nodes": retrieved_previews,
                        },
                        metadata={
                            "similarity_top_k": self.config.similarity_top_k,
                            "podcast_filter_applied": podcast_filter_applied,
                            "podcast": normalized_podcast,
                        },
                    )
                except Exception as exc:
                    self.logger.debug(f"Langfuse retrieve span update failed: {exc}")
        return retrieved_nodes

    async def _get_synthetized_answer(
        self,
        langfuse,
        enhanced_question: str,
        sorted_nodes,
    ):
        """Synthesize a final answer from retrieved nodes.

        Runs a LlamaIndex response synthesizer in `ResponseMode.COMPACT` over the
        provided nodes and records basic metrics to Langfuse (when available).

        Args:
            langfuse: Langfuse client used for tracing spans.
            enhanced_question: Question string (possibly augmented with context).
            sorted_nodes: Retrieved nodes after sorting/postprocessing.

        Returns:
            The synthesized response text.
        """
        synthesizer = get_response_synthesizer(
            response_mode=ResponseMode.COMPACT, llm=Settings.llm
        )
        try:
            synthesize_cm = langfuse.start_as_current_observation(
                as_type="span",
                name="rag.synthesize",
            )
        except Exception as exc:
            self.logger.debug(f"Langfuse synthesize span start failed: {exc}")
            synthesize_cm = contextlib.nullcontext()

        with synthesize_cm as synthesize_span:
            response = await synthesizer.asynthesize(enhanced_question, sorted_nodes)

            if synthesize_span is not None:
                try:
                    synthesize_span.update(
                        output={"response_length": len(str(response))},
                        metadata={
                            "response_mode": str(ResponseMode.COMPACT),
                            "llm_model": self.config.llm_model,
                        },
                    )
                except Exception as exc:
                    self.logger.debug(f"Langfuse synthesize span update failed: {exc}")

        self.logger.debug(f"Generated response: {len(str(response))} characters")
        return str(response)

    async def query(
        self,
        question: str,
        context: Optional[str] = None,
        *,
        podcast: Optional[str] = None,
    ) -> str:
        """
        Process a single query without conversation memory.

        Args:
            question: User's question in French
            context: Optional context from external conversation management
            podcast: Optional podcast name to filter retrieval (exact match on Qdrant payload `podcast`). If omitted, searches across all podcasts.

        Returns:
            Generated response in French

        Raises:
            Exception: If query processing fails
        """
        normalized_podcast = (podcast or "").strip() or None
        podcast_filter_applied = False
        retriever = self.retriever

        try:
            self.logger.debug(f"Processing query: {question[:50]}...")
            langfuse = get_langfuse()

            # If context is provided, combine it with the question
            if context:
                enhanced_question = f"Context: {context}\n\nQuestion: {question}"
            else:
                enhanced_question = question

            if normalized_podcast:
                self.logger.debug(f"Applying podcast filter: {normalized_podcast}")
                retriever_filters = MetadataFilters(
                    filters=[MetadataFilter(key="podcast", value=normalized_podcast)]
                )
                retriever = VectorIndexRetriever(
                    index=self.index,
                    similarity_top_k=self.config.similarity_top_k,
                    filters=retriever_filters,
                )
                podcast_filter_applied = True

            # First retrieve nodes
            retrieved_nodes = await self._retrieve_nodes(
                retriever,
                langfuse,
                enhanced_question,
                podcast_filter_applied,
                normalized_podcast,
            )

            # Apply temporal sorting if needed
            sorted_nodes = sort_nodes_temporally(retrieved_nodes, enhanced_question)

            # Apply postprocessors
            if hasattr(self, "postprocessors") and self.postprocessors:
                for postprocessor in self.postprocessors:
                    if hasattr(postprocessor, "postprocess_nodes"):
                        sorted_nodes = postprocessor.postprocess_nodes(sorted_nodes)

            # Synthesize
            response = await self._get_synthetized_answer(
                langfuse,
                enhanced_question,
                sorted_nodes,
            )
            return str(response)

        except Exception as e:
            self.logger.error(f"Query processing failed: {e}")
            # Fallback to original method if temporal sorting fails
            try:
                if context:
                    enhanced_question = f"Context: {context}\n\nQuestion: {question}"
                else:
                    enhanced_question = question
                query_engine = self.query_engine
                if podcast_filter_applied:
                    query_engine = RetrieverQueryEngine.from_args(
                        retriever=retriever,
                        node_postprocessors=self.postprocessors,
                    )
                response = await query_engine.aquery(enhanced_question)
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
