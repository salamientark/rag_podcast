import sys
import asyncio

from pathlib import Path
from urllib.parse import urlparse
from logging import getLogger

sys.path.insert(1, str(Path(__file__).resolve().parent.parent))

from src.db import get_db_session, Episode, ProcessingStage, update_episode_in_db
from src.storage.cloud import get_cloud_storage
from src.transcription.summarize import save_summary_to_cloud, summarize

logger = getLogger(__name__)


def get_transcript_content(transcript_url: str) -> str:
    """
    Fetch transcript content from the given URL.

    Parameters:
        url (str): The URL of the transcript.

    Returns:
        str: The content of the transcript.
    """
    try:
        # Get Client
        storage_engine = get_cloud_storage()
        client = storage_engine.get_client()

        parsed_url = urlparse(transcript_url)
        bucket_name = storage_engine.bucket_name
        key = parsed_url.path.lstrip("/").strip("/", 1)[1]
        response = client.get_object(Bucket=bucket_name, Key=key)
        return response["Body"].read().decode()
    except Exception as exc:
        logger.error(
            f"[fetch_transcript] Error during transcript fetch: {exc}", exc_info=True
        )
        raise


def get_episode_info() -> list[tuple[str, str, str, str]]:
    """
    Retrieve episode information from the database.
    Returns:
        list[tuple[str, str, str]]: A list of tuples containing episode ID, podcast name, and formatted transcript path.
    """
    episodes_info = []
    with get_db_session() as session:
        response = (
            session.query(Episode)
            .filter(Episode.processing_stage == ProcessingStage.EMBEDDED)
            .all()
        )
        for episode in response:
            episodes_info.append(
                (
                    episode.uuid,
                    episode.episode_id,
                    episode.podcast,
                    episode.formatted_transcript_path,
                )
            )
    return episodes_info


async def main():
    try:
        episodes_infos = get_episode_info()
        cloud_storage = get_cloud_storage()
        for uuid, episode_id, episode_podcast, transcript_url in episodes_infos:
            bucket_name = cloud_storage.bucket_name
            key = f"{episode_podcast}/summaries/episode_{episode_id}_summary.txt"
            content = get_transcript_content(transcript_url)
            summary = await summarize(content, language="fr")
            link = save_summary_to_cloud(bucket_name, key, summary)
            update_episode_in_db(
                uuid, podcast=episode_podcast, episode_id=episode_id, summary_path=link
            )
    except Exception as exc:
        logger.error(f"[main] Error in main execution: {exc}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
