#!/usr/bin/env python3
"""Reset episodes for re-transcription.

Usage:
    # Test with single episode
    uv run scripts/reset_episodes.py --podcast "Podcast Name" --episode-id 672

    # Reset all episodes (after confirming single works)
    uv run scripts/reset_episodes.py --podcast "Podcast Name" --all

    # Dry run to see what would be reset
    uv run scripts/reset_episodes.py --podcast "Podcast Name" --all --dry-run
"""

import argparse
import os
from dotenv import load_dotenv
from qdrant_client import models

from src.db import get_db_session, Episode, ProcessingStage, get_qdrant_client


def reset_episode(session, client, collection_name, episode, dry_run=False):
    """Reset a single episode."""
    print(f"  Episode {episode.episode_id}: {episode.title[:50]}...")
    print(f"    UUID: {episode.uuid}")
    print(f"    Current stage: {episode.processing_stage.value}")

    if dry_run:
        print("    [DRY RUN] Would reset to AUDIO_DOWNLOADED")
        print("    [DRY RUN] Would delete from Qdrant")
        return

    # 1. Delete from Qdrant
    client.delete(
        collection_name=collection_name,
        points_selector=models.FilterSelector(
            filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="db_uuid",
                        match=models.MatchValue(value=episode.uuid),
                    )
                ]
            )
        ),
    )
    print("    Deleted from Qdrant")

    # 2. Update DB stage
    episode.processing_stage = ProcessingStage.AUDIO_DOWNLOADED
    print("    Set to AUDIO_DOWNLOADED")


def main():
    parser = argparse.ArgumentParser(description="Reset episodes for re-transcription")
    parser.add_argument("--podcast", required=True, help="Podcast name")
    parser.add_argument("--episode-id", type=int, help="Single episode ID to reset")
    parser.add_argument("--all", action="store_true", help="Reset all episodes")
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview without changes"
    )
    args = parser.parse_args()

    if not args.episode_id and not args.all:
        print("Error: Must specify --episode-id or --all")
        return 1

    load_dotenv()
    collection_name = os.getenv("QDRANT_COLLECTION_NAME")
    if not collection_name:
        print("Error: QDRANT_COLLECTION_NAME not set in environment")
        return 1

    with get_db_session() as session:
        with get_qdrant_client() as client:
            # Build query
            query = session.query(Episode).filter(Episode.podcast.ilike(args.podcast))

            if args.episode_id:
                query = query.filter(Episode.episode_id == args.episode_id)

            episodes = query.all()

            if not episodes:
                print("No episodes found")
                return 1

            print(f"Found {len(episodes)} episode(s) to reset")
            print(f"Collection: {collection_name}")
            print("-" * 50)

            for episode in episodes:
                reset_episode(session, client, collection_name, episode, args.dry_run)

            if not args.dry_run:
                session.commit()
                print("-" * 50)
                print(f"Done! Reset {len(episodes)} episode(s)")
            else:
                print("-" * 50)
                print("[DRY RUN] No changes made")

    return 0


if __name__ == "__main__":
    exit(main())
