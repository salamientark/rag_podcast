"""
Configuration settings for RAGAS evaluation.

This module defines the EvaluationConfig dataclass with all configuration parameters
for the RAGAS-based RAG evaluation system.
"""

import os
from dataclasses import dataclass
from typing import List, Optional

from dotenv import load_dotenv

# Load environment variables at module import time
load_dotenv()


@dataclass
class EvaluationConfig:
    """Configuration for RAGAS evaluation of the RAG system"""

    # RAGAS evaluation metrics to use
    ragas_metrics: List[str] = None

    # LLM settings for RAGAS (uses same models as query system)
    llm_model: str = "claude-sonnet-4-20250514"
    embedding_model: str = "voyage-3.5"
    embedding_dimensions: int = 1024

    # API keys (inherited from environment)
    anthropic_api_key: Optional[str] = os.getenv("ANTHROPIC_API_KEY")
    voyage_api_key: Optional[str] = os.getenv("VOYAGE_API_KEY")

    # Evaluation settings
    batch_size: int = 5  # Process questions in batches to avoid rate limits
    max_retries: int = 3  # Retry failed evaluations

    # Output settings
    output_format: str = "both"  # "console", "csv", "langfuse", "both"
    export_to_langfuse: bool = True

    # Langfuse settings
    langfuse_public_key: Optional[str] = os.getenv("LANGFUSE_PUBLIC_KEY")
    langfuse_secret_key: Optional[str] = os.getenv("LANGFUSE_SECRET_KEY")

    def __post_init__(self):
        """Set default RAGAS metrics if not provided"""
        if self.ragas_metrics is None:
            # All comprehensive RAGAS metrics
            self.ragas_metrics = [
                "faithfulness",
                "answer_relevancy",
                "context_precision",
                "context_recall",
                "answer_semantic_similarity",
            ]

    def validate(self) -> List[str]:
        """
        Validate configuration and return any error messages.

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []

        if not self.anthropic_api_key:
            errors.append("ANTHROPIC_API_KEY is required for RAGAS evaluation")

        if not self.voyage_api_key:
            errors.append("VOYAGE_API_KEY is required for embedding model")

        if self.export_to_langfuse:
            if not self.langfuse_public_key:
                errors.append(
                    "LANGFUSE_PUBLIC_KEY is required when export_to_langfuse=True"
                )
            if not self.langfuse_secret_key:
                errors.append(
                    "LANGFUSE_SECRET_KEY is required when export_to_langfuse=True"
                )

        if self.batch_size < 1:
            errors.append("batch_size must be at least 1")

        valid_metrics = {
            "faithfulness",
            "answer_relevancy",
            "context_precision",
            "context_recall",
            "answer_semantic_similarity",
        }
        invalid_metrics = set(self.ragas_metrics) - valid_metrics
        if invalid_metrics:
            errors.append(f"Invalid RAGAS metrics: {invalid_metrics}")

        return errors


# System prompt for RAGAS LLM (French-aware)
RAGAS_SYSTEM_PROMPT_FR = """You are an evaluation assistant for a French podcast RAG system.

INSTRUCTIONS:
- Evaluate responses based on French podcast content
- Consider the conversational nature of podcast transcripts
- Account for French language nuances in your evaluation
- Be strict about factual accuracy and context grounding
- Consider semantic similarity even with different phrasing

EVALUATION CONTEXT:
- Source material: French tech podcast transcripts
- Response language: French
- Domain: Technology discussions, interviews, and analysis
- Format: Conversational and informal podcast content
"""
