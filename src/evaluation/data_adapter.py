"""
Data adapter for converting CSV testset to RAGAS Dataset format.

This module handles the conversion of the generated testset CSV to the format
required by RAGAS for evaluation, including parsing reference contexts and
preparing data structures for comprehensive RAG evaluation.
"""

import ast
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from datasets import Dataset

from src.logger import setup_logging

logger = setup_logging(
    logger_name="data_adapter",
    log_file="logs/evaluation.log",
    verbose=True,
)


class TestsetAdapter:
    """
    Adapter to convert CSV testset format to RAGAS Dataset format.

    Handles parsing of reference contexts stored as string representations
    of lists and prepares data for RAGAS evaluation metrics.
    """

    def __init__(self, csv_path: str):
        """
        Initialize the adapter with a CSV testset file.

        Args:
            csv_path: Path to the CSV testset file

        Raises:
            FileNotFoundError: If CSV file doesn't exist
            ValueError: If CSV format is invalid
        """
        self.csv_path = Path(csv_path)
        if not self.csv_path.exists():
            raise FileNotFoundError(f"Testset file not found: {csv_path}")

        self.df = None
        self._load_csv()

    def _load_csv(self):
        """Load and validate the CSV testset file."""
        try:
            self.df = pd.read_csv(self.csv_path)
            logger.info(
                f"Loaded testset with {len(self.df)} questions from {self.csv_path}"
            )

            # Clean NaN values to prevent conversion errors
            self.df = self.df.fillna("")

            # Validate required columns
            required_cols = ["user_input", "reference_contexts", "reference"]
            missing_cols = [col for col in required_cols if col not in self.df.columns]
            if missing_cols:
                raise ValueError(f"Missing required columns: {missing_cols}")

        except Exception as e:
            logger.error(f"Failed to load CSV testset: {e}")
            raise

    def _parse_reference_contexts(self, contexts_str: str) -> List[str]:
        """
        Parse reference contexts from string representation.

        The CSV stores reference_contexts as a string representation of a list.
        This method safely parses it back to a list of strings.

        Args:
            contexts_str: String representation of list of contexts

        Returns:
            List of context strings
        """
        try:
            # The contexts are stored as string representation of Python list
            contexts_list = ast.literal_eval(contexts_str)

            if not isinstance(contexts_list, list):
                logger.warning(
                    f"Expected list but got {type(contexts_list)}, converting to list"
                )
                contexts_list = [str(contexts_list)]

            # Ensure all items are strings
            contexts = [str(ctx).strip() for ctx in contexts_list if ctx]

            if not contexts:
                logger.warning("Empty contexts list after parsing")
                return ["No context available"]

            return contexts

        except (ValueError, SyntaxError) as e:
            logger.warning(f"Failed to parse contexts '{contexts_str[:100]}...': {e}")
            # Fallback: treat the whole string as a single context
            return [contexts_str.strip()]

    def to_ragas_dataset(self, limit: Optional[int] = None) -> Dataset:
        """
        Convert the CSV testset to RAGAS Dataset format.

        Args:
            limit: Optional limit on number of questions to include

        Returns:
            Dataset formatted for RAGAS evaluation with columns:
            - question: User questions from 'user_input'
            - contexts: Parsed reference contexts as List[str]
            - ground_truth: Reference answers from 'reference'
            - metadata: Additional information (persona, query style, etc.)
        """
        if self.df is None:
            raise RuntimeError("CSV not loaded. Call _load_csv() first.")

        # Apply limit if specified
        df_subset = self.df.head(limit) if limit else self.df
        logger.info(f"Converting {len(df_subset)} questions to RAGAS format")

        # Prepare RAGAS-compatible data structure (without metadata to avoid conversion errors)
        ragas_data = {"question": [], "contexts": [], "ground_truth": []}

        for idx, row in df_subset.iterrows():
            try:
                # Extract and clean question
                question = str(row["user_input"]).strip()
                if not question:
                    logger.warning(f"Empty question at row {idx}, skipping")
                    continue

                # Parse reference contexts - ensure it's a string
                contexts_str = (
                    str(row["reference_contexts"])
                    if pd.notna(row["reference_contexts"])
                    else ""
                )
                contexts = self._parse_reference_contexts(contexts_str)

                # Extract ground truth answer
                ground_truth = str(row["reference"]).strip()
                if not ground_truth:
                    logger.warning(f"Empty ground truth at row {idx}")
                    ground_truth = "No reference answer provided"

                # Prepare metadata - handle NaN values
                # metadata = {
                #     "persona_name": str(row.get("persona_name", "")).replace("nan", ""),
                #     "query_style": str(row.get("query_style", "")).replace("nan", ""),
                #     "query_length": str(row.get("query_length", "")).replace("nan", ""),
                #     "synthesizer_name": str(row.get("synthesizer_name", "")).replace(
                #         "nan", ""
                #     ),
                #     "row_index": idx,
                # }

                # Add to RAGAS data (without metadata to avoid conversion issues)
                ragas_data["question"].append(question)
                ragas_data["contexts"].append(contexts)
                ragas_data["ground_truth"].append(ground_truth)

            except Exception as e:
                logger.error(f"Failed to process row {idx}: {e}")
                continue

        # Create Dataset
        if not ragas_data["question"]:
            raise ValueError("No valid questions found in testset")

        dataset = Dataset.from_dict(ragas_data)
        logger.info(f"Created RAGAS dataset with {len(dataset)} questions")

        return dataset

    def get_questions_only(self, limit: Optional[int] = None) -> List[str]:
        """
        Extract just the questions for RAG system evaluation.

        Args:
            limit: Optional limit on number of questions

        Returns:
            List of question strings
        """
        if self.df is None:
            raise RuntimeError("CSV not loaded")

        df_subset = self.df.head(limit) if limit else self.df
        questions = df_subset["user_input"].astype(str).str.strip().tolist()

        # Filter out empty questions
        questions = [q for q in questions if q and q.lower() != "nan"]

        logger.info(f"Extracted {len(questions)} questions from testset")
        return questions

    def get_summary(self) -> Dict[str, Any]:
        """
        Get summary statistics about the testset.

        Returns:
            Dictionary with testset statistics
        """
        if self.df is None:
            return {"error": "CSV not loaded"}

        summary = {
            "total_questions": len(self.df),
            "columns": list(self.df.columns),
            "personas": self.df.get("persona_name", pd.Series())
            .value_counts()
            .to_dict(),
            "query_styles": self.df.get("query_style", pd.Series())
            .value_counts()
            .to_dict(),
            "query_lengths": self.df.get("query_length", pd.Series())
            .value_counts()
            .to_dict(),
        }

        # Check for empty values
        empty_questions = self.df["user_input"].isna().sum()
        empty_contexts = self.df["reference_contexts"].isna().sum()
        empty_references = self.df["reference"].isna().sum()

        summary["data_quality"] = {
            "empty_questions": int(empty_questions),
            "empty_contexts": int(empty_contexts),
            "empty_references": int(empty_references),
        }

        return summary


def load_testset_as_ragas_dataset(
    csv_path: str, limit: Optional[int] = None
) -> Dataset:
    """
    Convenience function to load testset CSV directly as RAGAS Dataset.

    Args:
        csv_path: Path to the CSV testset file
        limit: Optional limit on number of questions

    Returns:
        RAGAS Dataset ready for evaluation
    """
    adapter = TestsetAdapter(csv_path)
    return adapter.to_ragas_dataset(limit=limit)


def get_testset_questions(csv_path: str, limit: Optional[int] = None) -> List[str]:
    """
    Convenience function to extract questions from testset CSV.

    Args:
        csv_path: Path to the CSV testset file
        limit: Optional limit on number of questions

    Returns:
        List of question strings
    """
    adapter = TestsetAdapter(csv_path)
    return adapter.get_questions_only(limit=limit)
