"""
Direct conversational client for podcast queries.

This module provides the DirectChatClient class that wraps the core
PodcastQueryService with conversation management capabilities:
- LlamaIndex ChatMemoryBuffer for conversation history
- CondensePlusContextChatEngine for context-aware responses
- French system prompts and conversational flow
"""

import logging
from llama_index.core.memory import ChatMemoryBuffer
from llama_index.core.chat_engine import CondensePlusContextChatEngine

from .service import PodcastQueryService
from .config import QueryConfig, SYSTEM_PROMPT_FR
from .postprocessors import get_reranker


class DirectChatClient:
    """
    Conversational wrapper around PodcastQueryService.

    Provides stateful chat interface with memory management for direct CLI usage.
    Maintains conversation history and handles context condensation.
    """

    def __init__(self, query_service: PodcastQueryService, config: QueryConfig):
        """
        Initialize the direct chat client.

        Args:
            query_service: Initialized PodcastQueryService instance
            config: QueryConfig instance with conversation settings

        Raises:
            Exception: If chat engine setup fails
        """
        self.service = query_service
        self.config = config
        self.logger = logging.getLogger(__name__)

        try:
            self._setup_chat_engine()
            self.logger.info("Direct chat client initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize direct chat client: {e}")
            raise

    def _setup_chat_engine(self):
        """Configure conversational chat engine with memory"""
        # Build postprocessor pipeline (order matters!)
        postprocessors = []

        # Optional reranking with BGE-M3 (French-optimized)
        if self.config.use_reranking:
            reranker = get_reranker(
                model_name=self.config.rerank_model, top_n=self.config.rerank_top_n
            )
            postprocessors.append(reranker)
            self.logger.info(f"Chat reranking enabled with {self.config.rerank_model}")
        else:
            self.logger.info("Chat reranking disabled (faster responses)")

        # Conversation memory buffer
        memory = ChatMemoryBuffer.from_defaults(
            token_limit=self.config.memory_token_limit
        )

        # Create conversational chat engine
        self.chat_engine = CondensePlusContextChatEngine.from_defaults(
            retriever=self.service.retriever,
            node_postprocessors=postprocessors,
            memory=memory,
            system_prompt=SYSTEM_PROMPT_FR,
        )

        self.logger.info(
            f"Chat engine configured: memory={self.config.memory_token_limit} tokens"
        )

    async def chat(self, message: str) -> str:
        """
        Process a conversational message with memory context.

        Args:
            message: User's message in French

        Returns:
            Conversational response in French with context awareness

        Raises:
            Exception: If chat processing fails
        """
        try:
            self.logger.debug(f"Processing chat message: {message[:50]}...")
            response = await self.chat_engine.achat(message)
            self.logger.debug(
                f"Generated chat response: {len(str(response))} characters"
            )
            return str(response)

        except Exception as e:
            self.logger.error(f"Chat processing failed: {e}")
            raise

    def reset_conversation(self):
        """
        Clear conversation memory and start fresh.

        Useful for starting a new conversation topic or clearing context.
        """
        try:
            self.chat_engine.reset()
            self.logger.info("Conversation memory reset")
        except Exception as e:
            self.logger.error(f"Failed to reset conversation: {e}")
            raise

    def get_conversation_summary(self) -> dict:
        """
        Get information about the current conversation state.

        Returns:
            Dictionary with conversation metrics and status
        """
        return {
            "client_type": "conversational",
            "memory_token_limit": self.config.memory_token_limit,
            "reranking_enabled": self.config.use_reranking,
            "system_prompt": "French podcast assistant",
            "memory_status": "active",
        }

    def get_status(self) -> dict:
        """
        Get comprehensive status including service and conversation info.

        Returns:
            Dictionary with full client status
        """
        service_status = self.service.get_status()
        conversation_status = self.get_conversation_summary()

        return {
            **service_status,
            **conversation_status,
            "wrapper_type": "direct_chat_client",
        }


# Factory function for easy initialization
def create_direct_chat_client(config: QueryConfig) -> DirectChatClient:
    """
    Factory function to create a DirectChatClient with initialized service.

    Args:
        config: QueryConfig instance

    Returns:
        Initialized DirectChatClient ready for conversation

    Raises:
        Exception: If initialization fails
    """
    query_service = PodcastQueryService(config)
    return DirectChatClient(query_service, config)
