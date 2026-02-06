"""
Results analysis and reporting for RAGAS evaluation.

This module provides utilities for analyzing, visualizing, and reporting
RAGAS evaluation results, with integration to Langfuse for tracking.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from src.logger import setup_logging
from src.observability.langfuse import get_langfuse

logger = setup_logging(
    logger_name="evaluation_analysis",
    log_file="logs/evaluation.log",
    verbose=True,
)


class EvaluationAnalyzer:
    """
    Analyzer for RAGAS evaluation results.

    Provides statistical analysis, reporting, and export functionality
    for evaluation results.
    """

    def __init__(self, results: Dict[str, Any]):
        """
        Initialize the analyzer with evaluation results.

        Args:
            results: Dictionary containing RAGAS evaluation results
        """
        self.results = results
        self.metrics = results.get("metrics", {})
        self.config = results.get("config", {})
        self.timestamp = datetime.now().isoformat()

    def get_summary_stats(self) -> Dict[str, Any]:
        """
        Generate summary statistics for the evaluation.

        Returns:
            Dictionary with summary statistics
        """
        summary = {
            "evaluation_timestamp": self.timestamp,
            "total_questions": self.results.get("total_questions", 0),
            "total_eval_time": self.results.get("total_eval_time", 0),
            "num_batches": self.results.get("num_batches", 0),
            "podcast_filter": self.results.get("podcast_filter"),
            "testset_path": self.results.get("testset_path"),
        }

        # Add metric summaries
        if self.metrics:
            summary["metric_scores"] = {}
            summary["overall_performance"] = {}

            for metric_name, score in self.metrics.items():
                summary["metric_scores"][metric_name] = {
                    "score": round(float(score), 4),
                    "percentage": round(float(score) * 100, 2),
                }

            # Calculate overall performance indicators
            if len(self.metrics) > 0:
                avg_score = sum(self.metrics.values()) / len(self.metrics)
                summary["overall_performance"]["average_score"] = round(avg_score, 4)
                summary["overall_performance"]["average_percentage"] = round(
                    avg_score * 100, 2
                )

                # Performance categories
                if avg_score >= 0.8:
                    performance_level = "Excellent"
                elif avg_score >= 0.7:
                    performance_level = "Good"
                elif avg_score >= 0.6:
                    performance_level = "Fair"
                else:
                    performance_level = "Needs Improvement"

                summary["overall_performance"]["level"] = performance_level

        # Add configuration info
        summary["configuration"] = self.config

        return summary

    def analyze_metric_performance(self) -> Dict[str, Any]:
        """
        Detailed analysis of individual metric performance.

        Returns:
            Dictionary with detailed metric analysis
        """
        analysis = {
            "metrics_analysis": {},
            "strengths": [],
            "weaknesses": [],
            "recommendations": [],
        }

        for metric_name, score in self.metrics.items():
            metric_analysis = {
                "score": round(float(score), 4),
                "percentage": round(float(score) * 100, 2),
                "interpretation": self._interpret_metric(metric_name, score),
                "benchmark": self._get_metric_benchmark(metric_name),
            }

            # Determine if this is a strength or weakness
            if score >= 0.75:
                analysis["strengths"].append(
                    f"{metric_name}: {metric_analysis['interpretation']}"
                )
            elif score < 0.6:
                analysis["weaknesses"].append(
                    f"{metric_name}: {metric_analysis['interpretation']}"
                )

            analysis["metrics_analysis"][metric_name] = metric_analysis

        # Generate recommendations based on weaknesses
        analysis["recommendations"] = self._generate_recommendations(self.metrics)

        return analysis

    def _interpret_metric(self, metric_name: str, score: float) -> str:
        """
        Provide human-readable interpretation of metric scores.

        Args:
            metric_name: Name of the RAGAS metric
            score: Metric score (0-1)

        Returns:
            Human-readable interpretation
        """
        percentage = round(score * 100, 1)

        interpretations = {
            "faithfulness": {
                "high": f"Excellent faithfulness ({percentage}%) - responses are well-grounded in retrieved context",
                "medium": f"Good faithfulness ({percentage}%) - most responses are grounded, some minor issues",
                "low": f"Poor faithfulness ({percentage}%) - responses often contain ungrounded information",
            },
            "answer_relevancy": {
                "high": f"Excellent relevancy ({percentage}%) - answers directly address the questions",
                "medium": f"Good relevancy ({percentage}%) - answers are mostly relevant with minor off-topic content",
                "low": f"Poor relevancy ({percentage}%) - answers often miss the main question focus",
            },
            "context_precision": {
                "high": f"Excellent precision ({percentage}%) - most relevant contexts are ranked highest",
                "medium": f"Good precision ({percentage}%) - relevant contexts are generally well-ranked",
                "low": f"Poor precision ({percentage}%) - relevant contexts are not prioritized effectively",
            },
            "context_recall": {
                "high": f"Excellent recall ({percentage}%) - retrieval captures most relevant information",
                "medium": f"Good recall ({percentage}%) - retrieval captures most relevant information",
                "low": f"Poor recall ({percentage}%) - retrieval misses important relevant information",
            },
            "answer_semantic_similarity": {
                "high": f"High similarity ({percentage}%) - generated answers are semantically very similar to references",
                "medium": f"Moderate similarity ({percentage}%) - generated answers have reasonable semantic similarity",
                "low": f"Low similarity ({percentage}%) - generated answers differ significantly from references",
            },
        }

        # Determine performance level
        if score >= 0.75:
            level = "high"
        elif score >= 0.6:
            level = "medium"
        else:
            level = "low"

        return interpretations.get(metric_name, {}).get(
            level, f"{metric_name}: {percentage}%"
        )

    def _get_metric_benchmark(self, metric_name: str) -> Dict[str, float]:
        """
        Get benchmark scores for comparison.

        Args:
            metric_name: Name of the RAGAS metric

        Returns:
            Dictionary with benchmark thresholds
        """
        # These are general benchmarks - you might want to adjust based on your domain
        benchmarks = {
            "faithfulness": {"excellent": 0.8, "good": 0.7, "fair": 0.6},
            "answer_relevancy": {"excellent": 0.8, "good": 0.7, "fair": 0.6},
            "context_precision": {"excellent": 0.8, "good": 0.7, "fair": 0.6},
            "context_recall": {"excellent": 0.8, "good": 0.7, "fair": 0.6},
            "answer_semantic_similarity": {"excellent": 0.7, "good": 0.6, "fair": 0.5},
        }

        return benchmarks.get(metric_name, {"excellent": 0.8, "good": 0.7, "fair": 0.6})

    def _generate_recommendations(self, metrics: Dict[str, float]) -> List[str]:
        """
        Generate actionable recommendations based on metric scores.

        Args:
            metrics: Dictionary of metric scores

        Returns:
            List of recommendation strings
        """
        recommendations = []

        # Faithfulness recommendations
        if "faithfulness" in metrics and metrics["faithfulness"] < 0.6:
            recommendations.append(
                "Improve faithfulness by: enhancing retrieval quality, "
                "fine-tuning LLM prompts to stick closer to context, "
                "or implementing stricter context grounding checks"
            )

        # Answer relevancy recommendations
        if "answer_relevancy" in metrics and metrics["answer_relevancy"] < 0.6:
            recommendations.append(
                "Improve answer relevancy by: refining query understanding, "
                "improving question decomposition, or adjusting the generation prompt "
                "to focus more directly on the question"
            )

        # Context precision recommendations
        if "context_precision" in metrics and metrics["context_precision"] < 0.6:
            recommendations.append(
                "Improve context precision by: tuning embedding model parameters, "
                "implementing better reranking, or improving chunk quality and metadata"
            )

        # Context recall recommendations
        if "context_recall" in metrics and metrics["context_recall"] < 0.6:
            recommendations.append(
                "Improve context recall by: increasing retrieval top_k, "
                "improving embedding quality, expanding chunk overlap, "
                "or enhancing query expansion techniques"
            )

        # Semantic similarity recommendations
        if (
            "answer_semantic_similarity" in metrics
            and metrics["answer_semantic_similarity"] < 0.5
        ):
            recommendations.append(
                "Improve semantic similarity by: adjusting generation prompts, "
                "fine-tuning the LLM for domain-specific responses, "
                "or improving the quality of reference answers in the testset"
            )

        # General recommendations
        if not recommendations:
            recommendations.append(
                "Overall performance is good. Consider: monitoring performance over time, "
                "expanding the evaluation testset, or conducting qualitative analysis "
                "of edge cases"
            )

        return recommendations

    def export_detailed_csv(self, output_path: str) -> str:
        """
        Export detailed results to CSV.

        Args:
            output_path: Path for the output CSV file

        Returns:
            Path to the exported file
        """
        try:
            # Prepare detailed data
            export_data = []

            # Get questions and answers if available
            questions = self.results.get("generated_answers", [])
            contexts = self.results.get("retrieved_contexts", [])

            if questions:
                for i, answer in enumerate(questions):
                    row = {
                        "question_id": i + 1,
                        "generated_answer": answer,
                        "context_count": len(contexts[i]) if i < len(contexts) else 0,
                        "context_preview": (
                            contexts[i][0][:200] + "..."
                            if i < len(contexts) and contexts[i]
                            else ""
                        ),
                    }

                    # Add metric scores if available per question
                    for metric_name in self.metrics:
                        row[f"{metric_name}_score"] = self.metrics[metric_name]

                    export_data.append(row)
            else:
                # If no detailed data, export summary
                row = {
                    "evaluation_summary": "Complete evaluation results",
                    "total_questions": self.results.get("total_questions", 0),
                    "eval_time": self.results.get("total_eval_time", 0),
                }
                row.update(
                    {f"{name}_score": score for name, score in self.metrics.items()}
                )
                export_data.append(row)

            # Create DataFrame and export
            df = pd.DataFrame(export_data)
            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            df.to_csv(output_file, index=False)

            logger.info(f"Detailed results exported to {output_file}")
            return str(output_file)

        except Exception as e:
            logger.error(f"Failed to export CSV: {e}")
            raise

    def export_to_langfuse(self, project_name: str = "rag_podcast_evaluation") -> bool:
        """
        Export evaluation results to Langfuse for tracking.

        Args:
            project_name: Langfuse project name

        Returns:
            True if export successful, False otherwise
        """
        try:
            langfuse = get_langfuse()

            # Create evaluation trace
            trace = langfuse.trace(
                name="ragas_evaluation",
                metadata={
                    "evaluation_type": "comprehensive_ragas",
                    "timestamp": self.timestamp,
                    "testset_path": self.results.get("testset_path"),
                    "total_questions": self.results.get("total_questions"),
                    "podcast_filter": self.results.get("podcast_filter"),
                    "config": self.config,
                },
                tags=["evaluation", "ragas", "performance_analysis"],
            )

            # Add metric scores as events
            for metric_name, score in self.metrics.items():
                trace.event(
                    name=f"metric_score_{metric_name}",
                    metadata={
                        "metric": metric_name,
                        "score": float(score),
                        "percentage": round(float(score) * 100, 2),
                        "interpretation": self._interpret_metric(metric_name, score),
                    },
                )

            # Add analysis summary
            summary = self.get_summary_stats()
            analysis = self.analyze_metric_performance()

            trace.event(
                name="evaluation_summary",
                metadata={
                    "summary": summary,
                    "analysis": analysis,
                    "export_timestamp": datetime.now().isoformat(),
                },
            )

            # Flush to ensure data is sent
            langfuse.flush()

            logger.info("Results exported to Langfuse successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to export to Langfuse: {e}")
            return False

    def print_console_report(self):
        """Print a comprehensive console report of the evaluation results."""
        print("\n" + "=" * 80)
        print("COMPREHENSIVE RAGAS EVALUATION REPORT")
        print("=" * 80)

        # Basic info
        summary = self.get_summary_stats()
        print(f"\nEVALUATION OVERVIEW:")
        print(f"  Timestamp: {summary['evaluation_timestamp']}")
        print(f"  Testset: {summary.get('testset_path', 'Unknown')}")
        print(f"  Questions evaluated: {summary['total_questions']}")
        if summary.get("podcast_filter"):
            print(f"  Podcast filter: {summary['podcast_filter']}")
        print(f"  Total evaluation time: {summary['total_eval_time']:.2f} seconds")
        print(f"  Processing batches: {summary['num_batches']}")

        # Overall performance
        if "overall_performance" in summary:
            perf = summary["overall_performance"]
            print(f"\nOVERALL PERFORMANCE: {perf.get('level', 'Unknown')}")
            print(
                f"  Average score: {perf.get('average_score', 0):.4f} ({perf.get('average_percentage', 0):.1f}%)"
            )

        # Individual metrics
        print(f"\nMETRIC SCORES:")
        print("-" * 50)
        for metric_name, score in self.metrics.items():
            percentage = round(float(score) * 100, 1)
            # Simple performance indicator
            if score >= 0.8:
                indicator = "🟢 Excellent"
            elif score >= 0.7:
                indicator = "🟡 Good"
            elif score >= 0.6:
                indicator = "🟠 Fair"
            else:
                indicator = "🔴 Poor"

            print(f"  {metric_name:30}: {score:.4f} ({percentage:5.1f}%) {indicator}")

        # Analysis
        analysis = self.analyze_metric_performance()

        if analysis["strengths"]:
            print(f"\nSTRENGTHS:")
            for strength in analysis["strengths"]:
                print(f"  ✅ {strength}")

        if analysis["weaknesses"]:
            print(f"\nAREAS FOR IMPROVEMENT:")
            for weakness in analysis["weaknesses"]:
                print(f"  ⚠️  {weakness}")

        if analysis["recommendations"]:
            print(f"\nRECOMMENDATIONS:")
            for i, rec in enumerate(analysis["recommendations"], 1):
                print(f"  {i}. {rec}")

        # Configuration
        if self.config:
            print(f"\nCONFIGURATION:")
            for key, value in self.config.items():
                print(f"  {key}: {value}")

        print("\n" + "=" * 80)
        print("Report completed successfully!")


def analyze_evaluation_results(results: Dict[str, Any]) -> EvaluationAnalyzer:
    """
    Convenience function to create an analyzer from results.

    Args:
        results: RAGAS evaluation results dictionary

    Returns:
        EvaluationAnalyzer instance
    """
    return EvaluationAnalyzer(results)


def export_results_json(results: Dict[str, Any], output_path: str) -> str:
    """
    Export evaluation results to JSON format.

    Args:
        results: RAGAS evaluation results
        output_path: Path for output JSON file

    Returns:
        Path to exported file
    """
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # Add timestamp to results
    export_data = {
        "export_timestamp": datetime.now().isoformat(),
        "evaluation_results": results,
    }

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(export_data, f, indent=2, ensure_ascii=False)

    logger.info(f"Results exported to JSON: {output_file}")
    return str(output_file)
