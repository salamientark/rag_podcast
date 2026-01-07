"""
Configuration settings for the podcast query agent.

This module defines the QueryConfig dataclass with all configuration parameters
for the LlamaIndex-based podcast query system.
"""

import os
from dotenv import load_dotenv
from dataclasses import dataclass
from typing import Optional


@dataclass
class QueryConfig:
    """Configuration for the podcast query agent"""

    # Models
    llm_model: str = "claude-haiku-4-5"
    embedding_model: str = "voyage-3.5"  # VoyageAI model
    embedding_dimensions: int = 1024

    # Retrieval settings (optimized for Claude's 200k context window)
    similarity_top_k: int = 5  # Initial retrieval from Qdrant

    # Reranking removed to reduce image size
    # To re-enable: add sentence-transformers to deps and see postprocessors.py

    # Chat memory (3000 tokens = ~8-12 exchanges)
    memory_token_limit: int = 3000

    load_dotenv()
    # Qdrant connection
    collection_name: Optional[str] = os.getenv("QDRANT_COLLECTION_NAME")
    qdrant_url: Optional[str] = os.getenv("QDRANT_URL")
    qdrant_api_key: Optional[str] = os.getenv("QDRANT_API_KEY", None)

    # API keys
    anthropic_api_key: Optional[str] = os.getenv("ANTHROPIC_API_KEY")
    voyage_api_key: Optional[str] = os.getenv("VOYAGE_API_KEY")


# French system prompt for the LLM
SYSTEM_PROMPT_FR = """Vous êtes un assistant spécialisé dans l'analyse du contenu podcast français.

INSTRUCTIONS:
- Utilisez les informations des épisodes pour fournir des réponses complètes et conversationnelles
- Chaque extrait est précédé de métadonnées (épisode, titre, partie)
- Citez toujours vos sources en mentionnant l'épisode et le titre
- Si l'information n'existe pas dans les podcasts, dites-le clairement
- Répondez en français de manière naturelle et engageante
- Pour les questions sur plusieurs épisodes, synthétisez les informations

STYLE:
- Conversationnel et amical
- Structurez vos réponses avec des bullets si nécessaire
- Mentionnez les dates d'épisodes quand pertinent
- Soyez précis mais accessible"""
