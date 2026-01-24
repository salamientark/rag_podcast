import os
from dotenv import load_dotenv
import io

from logging import getLogger

from src.storage.cloud import get_cloud_storage
from src.llm.openai import get_openai_async_client, OPENAI_MODEL


logger = getLogger(__name__)
load_dotenv()


def make_file_url(bucket_name: str, key: str) -> str:
    """
    Construct a cloud storage file URL.

    Parameters:
        bucket_name (str): The name of the cloud storage bucket.
        key (str): The key (path) in the bucket.
    Returns:
        The constructed file URL.
    """
    # Format bucket name and key
    if bucket_name.endswith("/"):
        bucket_name = bucket_name[:-1]
    if key.startswith("/"):
        key = key[1:]
    endpoint = os.getenv("BUCKET_ENDPOINT")
    return f"{endpoint}/{bucket_name}/{key}"


async def summarize(text: str, language: str = "en") -> str:
    """Generate a structured episode summary from transcript text.

    Args:
        text: Transcript text to summarize.
        language: Output language (ISO-ish, e.g. "fr", "en"). Should be normalized.

    Returns:
        A Markdown summary with sections (Summary, Key points, Topics).

    Raises:
        ValueError: If the OpenAI client cannot be initialized or text is empty.
        Exception: Re-raises unexpected runtime errors from the LLM call.
    """
    if not text or not text.strip():
        raise ValueError("Cannot summarize empty or whitespace-only text")

    agent_prompt = "Summarize this podcast transcript in {language}. Markdown: Summary, Key points, Topics (bullets). No inventions. Keep it under 500 tokens long."

    try:
        # Init llm client
        llm = get_openai_async_client()
        if llm is None:
            raise ValueError("LLM client initialization failed.")

        # Ask for summary
        logger.info("Calling OpenAI for transcript summarization")
        response = await llm.responses.create(
            model=OPENAI_MODEL,
            instructions=agent_prompt.format(language=language),
            input=text,
            max_output_tokens=900,
        )

        logger.info("OpenAI returned summary")
        return response.output_text
    except Exception as exc:
        logger.error(
            f"[summarize] Error during text summarization: {exc}", exc_info=True
        )
        raise


def save_summary_to_cloud(bucket_name: str, key: str, summary: str) -> str:
    """
    Save the summary to cloud storage.
    Parameters:
        bucket_name (str): The name of the cloud storage bucket.
        key (str): The key (path) in the bucket where the summary will be saved.
        summary (str): The summary text to save.

    Returns:
        The URL of the saved summary in cloud storage.
    """
    try:
        # Get S3 client
        storage_engine = get_cloud_storage()
        client = storage_engine.get_client()

        # Create io.BytesIO object from summary
        file_stream = io.BytesIO(summary.encode("utf-8"))

        # Upload to cloud storage
        client.upload_fileobj(file_stream, bucket_name, key)

        return make_file_url(bucket_name, key)

    except Exception as exc:
        logger.error(
            f"[save_summary_to_cloud] Error saving summary: {exc}", exc_info=True
        )
        raise
