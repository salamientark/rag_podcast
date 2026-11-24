"""Resolve an episode's formatted transcript to a file on the local disk.

The database stores either a local path or a bucket URL in
`formatted_transcript_path`, depending on the storage flags used when the
episode was transcribed. Stages that read the transcript from disk (embedding)
go through this module so both forms work.
"""

import logging
import os
from pathlib import Path
from typing import Any

URL_PREFIXES = ("http://", "https://")


def local_transcript_path(podcast: str, episode_id: int) -> Path:
    """
    Build the canonical local path of an episode's formatted transcript.

    Args:
        podcast: Canonical podcast name.
        episode_id: Per-podcast episode number.

    Returns:
        Path under `data/{podcast}/transcripts/`.
    """
    return Path(
        f"data/{podcast}/transcripts/episode_{episode_id:03d}/"
        f"formatted_episode_{episode_id:03d}.txt"
    )


def _download_transcript(url: str) -> str:
    """
    Fetch a transcript from cloud storage.

    Args:
        url: Bucket URL of the transcript.

    Returns:
        The transcript text.
    """
    # Imported here so that local-only runs never need bucket credentials.
    from src.storage.cloud import CloudStorage

    return CloudStorage.get_transcript_content_from_url(url)


def resolve_local_transcript(episode: dict[str, Any]) -> Path | None:
    """
    Return a local file holding the episode's formatted transcript.

    A bucket URL is mapped to the canonical local path; the transcript is
    downloaded there when no non-empty local copy exists. An existing local
    copy wins: it is not compared with the bucket version.

    Args:
        episode: Episode dictionary with `podcast`, `episode_id` and
            `formatted_transcript_path`.

    Returns:
        Path of the local transcript, or None when the episode has no
        transcript yet.

    Raises:
        ValueError: If the URL does not belong to the configured bucket.
        botocore.exceptions.ClientError: If the download fails.
    """
    transcript_path = episode.get("formatted_transcript_path")
    if not transcript_path:
        return None
    if not str(transcript_path).startswith(URL_PREFIXES):
        return Path(transcript_path)

    local_path = local_transcript_path(episode["podcast"], episode["episode_id"])
    if local_path.exists() and local_path.stat().st_size > 0:
        return local_path

    logging.getLogger("pipeline").info(
        f"Downloading transcript for episode {episode['episode_id']:03d} to {local_path}"
    )
    content = _download_transcript(str(transcript_path))
    local_path.parent.mkdir(parents=True, exist_ok=True)
    # Write then rename, so an interrupted run never leaves a truncated copy
    # that later runs would trust.
    tmp_path = local_path.with_name(local_path.name + ".tmp")
    tmp_path.write_text(content, encoding="utf-8")
    os.replace(tmp_path, local_path)
    return local_path
