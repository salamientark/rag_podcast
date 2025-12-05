import os
from dotenv import load_dotenv
from openai import OpenAI


def init_llm_openai() -> OpenAI:
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
    except Exception as e:
        print(f"Error initializing OpenAI client: {e}")
        return None
