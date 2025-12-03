#!/usr/bin/env python3
"""
Main entry point for the ingestion package.

This allows running the sync_episodes script as a module with:
    uv run -m src.ingestion.sync_episodes

By default, if you run just:
    uv run -m src.ingestion

It will run the sync_episodes script as the default ingestion operation.
"""

from .sync_episodes import main

if __name__ == "__main__":
    main()
