"""
Postprocessors for the podcast query system.

This module provides:
- process_nodes_with_metadata: Injects episode metadata into chunks for LLM context
- sort_nodes_temporally: Sorts nodes by episode recency for temporal queries
- get_cohere_reranker: Creates a Cohere reranker postprocessor
"""

from typing import List
from llama_index.core.schema import NodeWithScore
from llama_index.postprocessor.cohere_rerank import CohereRerank


def get_cohere_reranker(
    api_key: str, model: str = "rerank-v3.5", top_n: int = 5
) -> CohereRerank:
    """
    Create a Cohere reranker postprocessor.

    Args:
        api_key: Cohere API key
        model: Cohere rerank model name (default: rerank-v3.5)
        top_n: Number of top results to return after reranking

    Returns:
        CohereRerank postprocessor instance
    """
    return CohereRerank(api_key=api_key, model=model, top_n=top_n)


def process_nodes_with_metadata(nodes: List[NodeWithScore]) -> List[NodeWithScore]:
    """
    Simple function to inject episode metadata into nodes.

    Args:
        nodes: List of retrieved nodes with scores

    Returns:
        List of nodes with metadata injected into content
    """
    for node in nodes:
        metadata = node.node.metadata

        # Extract metadata for LLM context
        episode_id = metadata.get("episode_id", "Unknown")
        title = metadata.get("title", "Unknown Episode")
        chunk_idx = metadata.get("chunk_index", 0)
        total_chunks = metadata.get("total_chunks", 1)

        # Build hidden context prefix for LLM
        context_prefix = f"[Episode {episode_id:03d}: {title}"

        # Add chunk information for multi-chunk episodes
        if total_chunks > 1:
            context_prefix += f" - Part {chunk_idx + 1}/{total_chunks}"

        context_prefix += "]\n\n"

        # Get original text using get_content() method
        try:
            original_text = node.node.get_content()
            # Create new text with metadata prefix
            new_text = context_prefix + original_text

            # Update the node content
            # We'll use the node's internal methods to update content
            from llama_index.core.schema import TextNode

            if isinstance(node.node, TextNode):
                # Create a new TextNode with updated content
                updated_node = TextNode(
                    text=new_text,
                    metadata=metadata,
                    id_=node.node.node_id,
                )
                node.node = updated_node
        except Exception:
            # If we can't modify the node, just continue
            pass

    return nodes


def sort_nodes_temporally(
    nodes: List[NodeWithScore], query: str
) -> List[NodeWithScore]:
    """
    Sort retrieved nodes by episode chronological order.

    For temporal queries (like "derniers episodes"), sorts by episode_id descending.
    For other queries, maintains original relevance-based order.

    Args:
        nodes: List of retrieved nodes with scores
        query: The original query string

    Returns:
        List of nodes sorted temporally if query suggests temporal intent
    """
    # Check if query suggests temporal intent (latest episodes)
    temporal_keywords = [
        "derniers",
        "dernier",
        "récent",
        "recent",
        "nouveau",
        "nouvelles",
    ]
    is_temporal_query = any(keyword in query.lower() for keyword in temporal_keywords)

    if is_temporal_query and nodes:
        # Sort by episode_id descending (assuming higher id = more recent)
        try:
            sorted_nodes = sorted(
                nodes,
                key=lambda node: node.node.metadata.get("episode_id", 0),
                reverse=True,
            )
            return sorted_nodes
        except Exception:
            # If sorting fails, return original order
            pass

    # Return original relevance-based order for non-temporal queries
    return nodes
