"""
Query module for podcast RAG system.

This module provides a French CLI interface for querying podcast episodes
using LlamaIndex with VoyageAI embeddings and Qdrant vector store.
"""

from .config import QueryConfig, SYSTEM_PROMPT_FR

__all__ = [
    "QueryConfig",
    "SYSTEM_PROMPT_FR",
]
