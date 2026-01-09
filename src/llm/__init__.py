"""This package contain modules related to large language models (LLMs).
base.py : Contain instruction prompts
openai.py : Contain OpenAI LLM initialization and utilities
"""

from .prompts import _speaker_identification_prompt
from .openai import (
    init_llm_openai,
    get_openai_async_client,
    get_openai_sync_client,
    OPENAI_MODEL,
)


__all__ = [
    "_speaker_identification_prompt",
    "init_llm_openai",
    "get_openai_async_client",
    "get_openai_sync_client",
    "OPENAI_MODEL",
]
