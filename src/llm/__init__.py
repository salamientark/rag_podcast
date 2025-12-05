"""This package contain modules related to large language models (LLMs).
base.py : Contain instruction prompts
openai.py : Contain OpenAI LLM initialization and utilities
"""

from .base import _speaker_identification_prompt
from .openai import init_llm_openai


__all__ = ["_speaker_identification_prompt", "init_llm_openai"]
