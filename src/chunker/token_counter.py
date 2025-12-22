"""Token counting utilities for text processing and API calls.

This module provides functions to count tokens in text strings using tiktoken,
which is compatible with OpenAI and similar models. For Voyage AI embeddings,
token counts are approximate but sufficient for pre-flight validation.
"""

import logging

import tiktoken


# Voyage AI model limits (as of Dec 2025)
VOYAGE_LIMITS = {
    "voyage-3.5": {"context_length": 32000, "batch_total": 320000, "batch_size": 1000},
    "voyage-3.5-lite": {
        "context_length": 32000,
        "batch_total": 1000000,
        "batch_size": 1000,
    },
    "voyage-3-large": {
        "context_length": 32000,
        "batch_total": 120000,
        "batch_size": 1000,
    },
    "voyage-3": {"context_length": 32000, "batch_total": 120000, "batch_size": 1000},
    "voyage-code-3": {
        "context_length": 32000,
        "batch_total": 120000,
        "batch_size": 1000,
    },
}


def count_tokens(text: str, encoding_name: str = "cl100k_base") -> int:
    """Count the number of tokens in a text string.

    Uses tiktoken to provide accurate token counts compatible with OpenAI models
    and approximate counts for other models like Voyage AI embeddings.

    Args:
        text: The text string to count tokens for.
        encoding_name: The encoding to use. Options:
            - "cl100k_base" (default): Used by GPT-4, GPT-3.5-turbo, text-embedding-ada-002
            - "p50k_base": Used by older models like text-davinci-003
            - "r50k_base": Used by older models like davinci

    Returns:
        The number of tokens in the text.

    Raises:
        ValueError: If the encoding_name is not recognized.

    Example:
        >>> count_tokens("Hello, world!")
        4
        >>> count_tokens("This is a longer text with more tokens.", encoding_name="cl100k_base")
        10
    """
    try:
        encoding = tiktoken.get_encoding(encoding_name)
    except ValueError as e:
        raise ValueError(f"Invalid encoding name: {encoding_name}") from e

    return len(encoding.encode(text))


def truncate_to_tokens(
    text: str, max_tokens: int, encoding_name: str = "cl100k_base"
) -> str:
    """Truncate text to fit within a maximum token count.

    Args:
        text: The text string to truncate.
        max_tokens: The maximum number of tokens allowed.
        encoding_name: The encoding to use (see count_tokens for options).

    Returns:
        The truncated text string that fits within max_tokens.

    Example:
        >>> truncate_to_tokens("This is a very long text...", max_tokens=5)
        'This is a very long'
    """
    encoding = tiktoken.get_encoding(encoding_name)
    tokens = encoding.encode(text)

    if len(tokens) <= max_tokens:
        return text

    truncated_tokens = tokens[:max_tokens]
    return encoding.decode(truncated_tokens)


def check_voyage_limits(
    texts: str | list[str],
    model: str = "voyage-3.5",
    encoding_name: str = "cl100k_base",
) -> dict[str, bool | int | list[str] | dict[str, int]]:
    """Check if text(s) fit within Voyage AI model limits.

    Args:
        texts: A single text string or list of text strings.
        model: The Voyage AI model name (default: "voyage-3.5").
        encoding_name: The encoding to use for token counting.

    Returns:
        A dictionary containing:
            - "fits": Whether all texts fit within limits (bool)
            - "total_tokens": Total token count across all texts (int)
            - "num_texts": Number of texts (int)
            - "max_text_tokens": Token count of longest text (int)
            - "issues": List of any limit violations (list[str])
            - "model_limits": The limits for the specified model (dict)

    Raises:
        ValueError: If the model name is not recognized.

    Example:
        >>> result = check_voyage_limits("Sample text", model="voyage-3.5")
        >>> print(result["fits"])
        True
        >>> print(result["total_tokens"])
        3
    """
    logger = logging.getLogger(__name__)

    if model not in VOYAGE_LIMITS:
        raise ValueError(
            f"Unknown Voyage AI model: {model}. "
            f"Available models: {list(VOYAGE_LIMITS.keys())}"
        )

    limits = VOYAGE_LIMITS[model]
    texts_list = [texts] if isinstance(texts, str) else texts

    # Count tokens for each text
    token_counts = [count_tokens(text, encoding_name) for text in texts_list]
    total_tokens = sum(token_counts)
    max_tokens = max(token_counts) if token_counts else 0
    num_texts = len(texts_list)

    # Check limits
    issues = []
    if max_tokens > limits["context_length"]:
        issues.append(
            f"Longest text has {max_tokens} tokens, exceeds context length limit of {limits['context_length']}"
        )
    if total_tokens > limits["batch_total"]:
        issues.append(
            f"Total tokens {total_tokens} exceeds batch total limit of {limits['batch_total']}"
        )
    if num_texts > limits["batch_size"]:
        issues.append(
            f"Number of texts {num_texts} exceeds batch size limit of {limits['batch_size']}"
        )

    fits = len(issues) == 0

    if not fits:
        logger.warning(f"Voyage AI limit check failed for model {model}: {issues}")

    return {
        "fits": fits,
        "total_tokens": total_tokens,
        "num_texts": num_texts,
        "max_text_tokens": max_tokens,
        "issues": issues,
        "model_limits": limits,
    }
