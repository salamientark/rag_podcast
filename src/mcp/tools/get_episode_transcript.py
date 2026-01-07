"""MCP tool: `get_episode_transcript`.

This tool retrieves the full transcript text for a specific episode by date.

Data sources:
- PostgreSQL: episode metadata (used to locate `formatted_transcript_path`)
- Object storage / local filesystem: transcript file retrieval

Use it when:
- A user asks about a precise episode (by date, or after you determine the date).

For content questions across multiple episodes, use `ask_podcast`.
"""

import logging
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.parse import urlparse
from urllib.request import urlopen

from src.storage.cloud import CloudStorage

from ..config import mcp
from .get_episode_info import get_episode_info_by_date

logger = logging.getLogger(__name__)


async def fetch_transcript(transcript_location: str) -> str:
    """Fetch transcript content from local path or cloud URL.

    Args:
        transcript_location: Local path, object-storage key, or absolute URL to the transcript.

    Returns:
        The transcript content as text.

    Raises:
        Exception: Re-raises any unexpected runtime errors.
    """
    path_candidate = Path(transcript_location)
    if path_candidate.exists():
        return path_candidate.read_text(encoding="utf-8")

    parsed = urlparse(transcript_location)

    # If a URL is provided, try fetching via cloud credentials first (more reliable).
    if parsed.scheme in ("http", "https"):
        key = parsed.path.lstrip("/")
        try:
            storage_engine = CloudStorage()
            client = storage_engine.get_client()
            bucket_name = storage_engine.bucket_name
            if bucket_name:
                with NamedTemporaryFile(suffix=".txt", delete=False) as tmp:
                    tmp_path = Path(tmp.name)

                client.download_file(bucket_name, key, str(tmp_path))
                content = tmp_path.read_text(encoding="utf-8")
                tmp_path.unlink(missing_ok=True)
                return content
        except Exception:
            # Fallback to a direct HTTP fetch (works if the transcript is publicly accessible).
            with urlopen(transcript_location) as response:  # noqa: S310
                return response.read().decode("utf-8")

    # Otherwise, assume the value is an object-storage key.
    try:
        storage_engine = CloudStorage()
        client = storage_engine.get_client()
        bucket_name = storage_engine.bucket_name
        if not bucket_name:
            raise RuntimeError("CloudStorage bucket name is not configured")

        key = transcript_location.lstrip("/")
        with NamedTemporaryFile(suffix=".txt", delete=False) as tmp:
            tmp_path = Path(tmp.name)

        client.download_file(bucket_name, key, str(tmp_path))
        content = tmp_path.read_text(encoding="utf-8")
        tmp_path.unlink(missing_ok=True)
        return content
    except Exception as exc:
        logger.error(
            f"[fetch_transcript] Error during transcript fetch: {exc}", exc_info=True
        )
        raise


@mcp.tool()
async def get_episode_transcript(date: str) -> str:
    """Return the full transcript for the episode published on the given date.

    Args:
        date: Date string in various formats (YYYY-MM-DD, YYYY-MM-DDTHH:MM:SS, etc.).

    Returns:
        Transcript text, or an error message.

    Raises:
        Exception: Re-raises any unexpected runtime errors.
    """
    try:
        logger.info(
            f"[get_episode_transcript] Looking for episode published on {date}..."
        )

        episode_info = get_episode_info_by_date(date)
        if episode_info is None:
            return (
                f"error: no episode found for date '{date}'. please check the date format "
                "(yyyy-mm-dd) and try again."
            )

        transcript_location = episode_info.get("formatted_transcript_path")
        if not transcript_location:
            return f"error: no formatted transcript found for episode on date '{date}'."

        return await fetch_transcript(transcript_location)
    except Exception as exc:
        logger.error(
            f"[get_episode_transcript] Error during transcript retrieval: {exc}",
            exc_info=True,
        )
        raise
