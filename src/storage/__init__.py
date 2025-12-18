"""
Storage module for handling local and cloud storage operations.

This module provides abstract and concrete implementations for storage
backends, supporting both local filesystem and cloud storage services.
"""

from .base import BaseStorage
from .cloud import CloudStorage
from .local import LocalStorage

__all__ = [
    "BaseStorage",
    "CloudStorage",
    "LocalStorage",
]
