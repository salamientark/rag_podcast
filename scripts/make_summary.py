import sys
import asyncio

from pathlib import Path
from logging import getLogger

sys.path.insert(1, str(Path(__file__).resolve().parent.parent))

from src.db import get_db_session, Episode, ProcessingStage, update_episode_in_db
from src.storage.cloud import get_cloud_storage, CloudStorage
from src.transcription.summarize import save_summary_to_cloud, summarize

logger = getLogger(__name__)


def get_episode_info() -> list[tuple[str, str, str, str]]:
    """
    Retrieve episode information from the database.
    Returns:
        list[tuple[str, str, str, str]]: A list of tuples containing episode uuid, ID, podcast name, and formatted transcript path.
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
            key = f"{episode_podcast}/summaries/episode_{episode_id:03d}_summary.txt"
            content = CloudStorage.get_transcript_content(transcript_url)
            if not content or not content.strip():
                logger.warning(
                    f"Episode {episode_id:03d} has empty transcript content, skipping."
                )
                continue
            summary = await summarize(content)
            link = save_summary_to_cloud(bucket_name, key, summary)
            update_episode_in_db(
                uuid, podcast=episode_podcast, episode_id=episode_id, summary_path=link
            )
    except Exception as exc:
        logger.error(f"[main] Error in main execution: {exc}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
