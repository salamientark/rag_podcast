# Evaluation Module

## Purpose

The `evaluation` module provides comprehensive RAGAS-based evaluation for the RAG podcast system. It evaluates retrieval quality, answer generation, and overall system performance using industry-standard metrics.

## Architecture

```
src/evaluation/
├── __init__.py           # Module exports
├── config.py            # Evaluation configuration
├── data_adapter.py      # CSV to RAGAS dataset conversion
├── evaluate_ragas.py    # Main evaluation engine
├── analysis.py          # Results analysis and reporting
└── CLAUDE.md           # This documentation
```

## Key Components

### EvaluationConfig (`config.py`)

**Configuration management for RAGAS evaluation:**

- RAGAS metrics selection (all 5 comprehensive metrics by default)
- LLM and embedding model settings (aligned with query system)
- Batch processing and rate limiting configuration
- Output format and Langfuse integration settings

### TestsetAdapter (`data_adapter.py`)

**CSV testset to RAGAS format converter:**

- Parses reference contexts from string representation
- Handles data quality issues (empty values, parsing errors)
- Creates RAGAS-compatible Dataset objects
- Provides summary statistics and quality checks

### RAGASEvaluator (`evaluate_ragas.py`)

**Main evaluation engine with comprehensive RAGAS metrics:**

- **Faithfulness**: Measures if answers are grounded in retrieved context
- **Answer Relevancy**: Evaluates how well answers address questions
- **Context Precision**: Assesses ranking of retrieved contexts
- **Context Recall**: Measures completeness of retrieval
- **Answer Semantic Similarity**: Compares generated vs reference answers

### EvaluationAnalyzer (`analysis.py`)

**Results analysis and reporting:**

- Statistical analysis with benchmarks and interpretations
- Console reports with visual indicators
- CSV and JSON export capabilities
- Langfuse integration for tracking over time

## RAGAS Metrics Explained

### 1. Faithfulness (Ground Truth Required: ❌)
- **What it measures**: Whether generated answers contain information that can be verified from the retrieved context
- **Scale**: 0-1 (higher is better)
- **Interpretation**: 
  - 0.8+ = Excellent (responses well-grounded)
  - 0.6-0.8 = Good (mostly grounded, minor issues)
  - <0.6 = Poor (frequent ungrounded information)

### 2. Answer Relevancy (Ground Truth Required: ❌)  
- **What it measures**: How well the generated answer addresses the original question
- **Scale**: 0-1 (higher is better)
- **Interpretation**:
  - 0.8+ = Excellent (directly addresses question)
  - 0.6-0.8 = Good (mostly relevant, minor off-topic)
  - <0.6 = Poor (often misses question focus)

### 3. Context Precision (Ground Truth Required: ✅)
- **What it measures**: Whether relevant contexts are ranked higher than irrelevant ones
- **Scale**: 0-1 (higher is better)
- **Interpretation**:
  - 0.8+ = Excellent (relevant contexts ranked highest)
  - 0.6-0.8 = Good (generally good ranking)
  - <0.6 = Poor (relevant contexts not prioritized)

### 4. Context Recall (Ground Truth Required: ✅)
- **What it measures**: What fraction of relevant information is successfully retrieved
- **Scale**: 0-1 (higher is better)  
- **Interpretation**:
  - 0.8+ = Excellent (captures most relevant info)
  - 0.6-0.8 = Good (captures most relevant info)
  - <0.6 = Poor (misses important information)

### 5. Answer Semantic Similarity (Ground Truth Required: ✅)
- **What it measures**: Semantic similarity between generated and reference answers
- **Scale**: 0-1 (higher is better)
- **Interpretation**:
  - 0.7+ = High similarity to reference answers
  - 0.5-0.7 = Moderate similarity 
  - <0.5 = Low similarity (significantly different)

## Usage Examples

### Basic Evaluation
```bash
# Evaluate entire testset
uv run -m src.evaluation.evaluate_ragas --testset data/testset.csv

# Limited evaluation for testing
uv run -m src.evaluation.evaluate_ragas --testset data/testset.csv --limit 5

# Podcast-specific evaluation  
uv run -m src.evaluation.evaluate_ragas --testset data/testset.csv --podcast "Le rendez-vous Tech"
```

### Advanced Usage
```bash
# Custom batch size (for rate limit management)
uv run -m src.evaluation.evaluate_ragas --testset data/testset.csv --batch-size 3

# Export detailed results
uv run -m src.evaluation.evaluate_ragas --testset data/testset.csv --output data/eval_results.csv

# Combined: limited evaluation with export
uv run -m src.evaluation.evaluate_ragas --testset data/testset.csv --limit 10 --output data/test_results.csv
```

### Programmatic Usage
```python
from src.evaluation import RAGASEvaluator, EvaluationConfig, analyze_evaluation_results

# Configure evaluation
config = EvaluationConfig(batch_size=3, export_to_langfuse=True)

# Initialize evaluator
evaluator = RAGASEvaluator(config)

# Run evaluation
results = await evaluator.evaluate_testset("data/testset.csv", limit=5)

# Analyze results
analyzer = analyze_evaluation_results(results)
analyzer.print_console_report()
analyzer.export_detailed_csv("results.csv")
```

## Configuration & Environment

### Required Environment Variables
```bash
# Core API Keys (required)
ANTHROPIC_API_KEY=xxx          # For LLM evaluation
VOYAGE_API_KEY=xxx             # For embeddings
COHERE_API_KEY=xxx             # For reranking in query service

# Database (required for query service)
QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION_NAME=podcast_episodes

# Optional: Langfuse tracking
LANGFUSE_PUBLIC_KEY=xxx
LANGFUSE_SECRET_KEY=xxx
```

### Configuration Options
```python
EvaluationConfig(
    ragas_metrics=["faithfulness", "answer_relevancy", ...],  # Which metrics to use
    batch_size=5,                    # Questions per batch (rate limiting)
    max_retries=3,                   # Retry failed evaluations
    export_to_langfuse=True,         # Export results to Langfuse
    llm_model="claude-sonnet-4-20250514",    # LLM for evaluation
    embedding_model="voyage-3.5",    # Embedding model
)
```

## Integration with Existing System

### Query Service Integration
- Uses existing `PodcastQueryService` for RAG response generation
- Inherits Qdrant connection and configuration from query system
- Maintains consistency with production pipeline

### Langfuse Integration  
- Exports evaluation results as traces for long-term tracking
- Integrates with existing observability setup
- Tracks metric scores and performance over time

### Context Length Fix
- Fixed `LANGFUSE_CONTEXT_SIZE` from 4000 to 8000 characters
- Ensures full context is captured for accurate evaluation
- Balances context completeness with token costs

## Output Formats

### Console Report
```
COMPREHENSIVE RAGAS EVALUATION REPORT
=====================================

EVALUATION OVERVIEW:
  Questions evaluated: 69
  Total evaluation time: 245.67 seconds
  
OVERALL PERFORMANCE: Good
  Average score: 0.7234 (72.3%)

METRIC SCORES:
  faithfulness           : 0.7892 (78.9%) 🟡 Good
  answer_relevancy       : 0.8123 (81.2%) 🟢 Excellent
  context_precision      : 0.6891 (68.9%) 🟡 Good
  context_recall         : 0.6234 (62.3%) 🟠 Fair
  answer_semantic_similarity: 0.7034 (70.3%) 🟡 Good

STRENGTHS:
  ✅ answer_relevancy: Excellent relevancy (81.2%) - answers directly address the questions

AREAS FOR IMPROVEMENT:  
  ⚠️  context_recall: Fair recall (62.3%) - retrieval misses some important relevant information

RECOMMENDATIONS:
  1. Improve context recall by: increasing retrieval top_k, improving embedding quality...
```

### CSV Export
- Detailed per-question results
- Individual metric scores (when available)
- Generated answers and context counts
- Question metadata and characteristics

### Langfuse Export
- Evaluation traces with full metadata
- Individual metric events with interpretations
- Performance tracking over time
- Integration with existing observability

## Performance Considerations

### Rate Limiting
- Processes questions in configurable batches (default: 5)
- Adds delays between API calls to avoid rate limits
- Implements retry logic for failed evaluations

### Memory Management
- Streams large testsets in batches
- Avoids loading all data into memory simultaneously
- Aggregates results efficiently across batches

### Cost Optimization  
- Uses same models as production system (no additional model costs)
- Configurable batch sizes to balance speed vs cost
- Optional limiting for testing and development

## Known Limitations & Future Improvements

### Current Limitations
1. **Context Extraction**: Currently parses contexts from markdown response format. A more structured approach would be better.
2. **Answer Generation**: Uses the full query service response as the "answer". Separating retrieval and generation would enable more precise evaluation.
3. **Batch Aggregation**: Simplified metric aggregation across batches. More sophisticated statistical aggregation could be implemented.

### Potential Improvements  
1. **Structured Response Format**: Modify query service to return structured data with separate contexts and generated answers
2. **Per-Question Metrics**: Store and analyze individual metric scores per question for deeper insights
3. **Automated Benchmarking**: Regular evaluation runs with performance alerts
4. **Custom Metrics**: Domain-specific metrics for podcast content evaluation

## Troubleshooting

### Common Issues
1. **API Rate Limits**: Reduce `batch_size` in configuration
2. **Empty Contexts**: Check that testset reference_contexts are properly formatted
3. **Langfuse Export Failures**: Verify LANGFUSE_* environment variables
4. **Memory Issues**: Use `--limit` parameter for large testsets

### Debug Mode
```bash
# Enable debug logging
PYTHONPATH=. python -m src.evaluation.evaluate_ragas --testset data/testset.csv --limit 1
```

This comprehensive evaluation system provides deep insights into your RAG system's performance and actionable recommendations for improvement.