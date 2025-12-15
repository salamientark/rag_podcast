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
    llm_model: str = "gpt-4o"
    embedding_model: str = "voyage-3.5"  # VoyageAI model
    embedding_dimensions: int = 1024

    # Retrieval settings (balanced performance)
    similarity_top_k: int = 10  # Initial retrieval from Qdrant
    rerank_top_n: int = 5  # After reranking

    # Reranking (disabled by default for simplicity)
    use_reranking: bool = False  # Start simple, enable for better quality
    rerank_model: str = "BAAI/bge-reranker-v2-m3"  # Free multilingual reranker

    # Chat memory (3000 tokens = ~8-12 exchanges)
    memory_token_limit: int = 3000

    load_dotenv()
    # Qdrant connection
    collection_name: Optional[str] = os.getenv("QDRANT_COLLECTION_NAME", "podcasts")
    qdrant_url: Optional[str] = os.getenv("QDRANT_URL", "http://localhost:6333")

    # API keys
    openai_api_key: Optional[str] = os.getenv("OPENAI_API_KEY")
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
