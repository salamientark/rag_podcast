import os
from dotenv import load_dotenv
from openai import OpenAI, AsyncOpenAI

OPENAI_MODEL = "gpt-5.2"

_async_client: AsyncOpenAI | None = None
_sync_client: OpenAI | None = None


def init_llm_openai() -> OpenAI | None:
    """
    Initialize OpenAI LLM client.

    Returns:
        OpenAI LLM client instance
    """
    try:
        env = load_dotenv()
        openai_api_key = os.environ.get("OPENAI_API_KEY")
        if not env or not openai_api_key:
            raise ValueError("OPENAI_API_KEY not found in environment variables.")
        client = OpenAI(
            api_key=openai_api_key,
        )
        return client
    except ValueError as e:
        print(f"Environment configuration error: {e}")
        return None
    except (OSError, IOError) as e:
        print(f"Failed to load environment file: {e}")
        return None


def init_llm_openai_async() -> AsyncOpenAI | None:
    """
    Initialize OpenAI LLM client.

    Returns:
        OpenAI LLM client instance
    """
    try:
        env = load_dotenv()
        openai_api_key = os.environ.get("OPENAI_API_KEY")
        if not env or not openai_api_key:
            raise ValueError("OPENAI_API_KEY not found in environment variables.")
        async_client = AsyncOpenAI(
            api_key=openai_api_key,
        )
        return async_client
    except ValueError as e:
        print(f"Environment configuration error: {e}")
        return None
    except (OSError, IOError) as e:
        print(f"Failed to load environment file: {e}")
        return None


def get_openai_async_client() -> AsyncOpenAI | None:
    global _async_client
    if _async_client is None:
        _async_client = init_llm_openai_async()
    return _async_client


def get_openai_sync_client() -> OpenAI | None:
    global _sync_client
    if _sync_client is None:
        _sync_client = init_llm_openai()
    return _sync_client
