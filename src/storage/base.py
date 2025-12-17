from abc import ABC, abstractmethod
from typing import Optional


class BaseStorage(ABC):
    """
    Abstract base class for storage interface.

    This class defines the common interface for both local and cloud storage
    implementations, providing methods for workspace creation and file operations.
    """

    @abstractmethod
    def check_file_existance(self, workspace: str, filename: str) -> bool:
        """
        Check if a file exists.

        Args:
            workspace (str): The workspace (prefix) path.
            filename (str): The name of the file.

        Returns:
            bool: True if the file exists, False otherwise.
        """

    @abstractmethod
    def create_episode_workspace(self, episode_id: Optional[int]) -> str:
        """Creates a workspace (prefix) for an episode.

        Args:
            episode_id (Optional[int]): The ID of the episode. Can be None.

        Returns:
            str: The workspace path/prefix for the episode.

        Raises:
            RuntimeError: If workspace creation fails.
        """
        pass

    @abstractmethod
    def save_file(self, workspace: str, filename: str, content: str) -> str:
        """Saves a file to the specified workspace.

        Args:
            workspace (str): The workspace (prefix) path.
            filename (str): The name of the file to save.
            content (str): The content to save.

        Returns:
            str: The full path or URL of the saved file.

        Raises:
            RuntimeError: If file saving fails.
        """
        pass

    @abstractmethod
    def _get_absolute_filename(self, workspace: str, filename: str) -> str:
        """Constructs the absolute filename/path.

        Args:
            workspace (str): The workspace (prefix) path.
            filename (str): The name of the file.

        Returns:
            str: The absolute filename/path.
        """
        pass
