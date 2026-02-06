"""
RAG Evaluation Module

This module provides comprehensive evaluation capabilities for the RAG podcast system
using RAGAS (Retrieval-Augmented Generation Assessment) metrics.

Key Components:
- TestsetAdapter: Convert CSV testset to RAGAS format
- RAGASEvaluator: Main evaluation engine with all RAGAS metrics
- EvaluationAnalyzer: Results analysis and reporting
- EvaluationConfig: Configuration management

Usage:
    # Basic evaluation
    uv run -m src.evaluation.evaluate_ragas --testset data/testset.csv

    # Limited evaluation for testing
    uv run -m src.evaluation.evaluate_ragas --testset data/testset.csv --limit 5

    # Podcast-specific evaluation
    uv run -m src.evaluation.evaluate_ragas --testset data/testset.csv --podcast "Le rendez-vous Tech"

    # Export results
    uv run -m src.evaluation.evaluate_ragas --testset data/testset.csv --output data/results.csv
"""

from .analysis import (
    EvaluationAnalyzer,
    analyze_evaluation_results,
    export_results_json,
)
from .config import EvaluationConfig, RAGAS_SYSTEM_PROMPT_FR
from .data_adapter import (
    TestsetAdapter,
    load_testset_as_ragas_dataset,
    get_testset_questions,
)
from .evaluate_ragas import RAGASEvaluator

__all__ = [
    "EvaluationConfig",
    "RAGAS_SYSTEM_PROMPT_FR",
    "TestsetAdapter",
    "load_testset_as_ragas_dataset",
    "get_testset_questions",
    "RAGASEvaluator",
    "EvaluationAnalyzer",
    "analyze_evaluation_results",
    "export_results_json",
]
