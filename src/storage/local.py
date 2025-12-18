import os
from typing import Optional


class LocalStorage:
    """A client for interacting with cloud storage services. (DigitalOcean)"""

    def file_exist(self, workspace: str, filename: str) -> bool:
        """
        Check if a file exists in local storage

        Args:
            workspace (str): The workspace (prefix) path.
            filename (str): The name of the file.

        Returns:
            bool: True if the file exists, False otherwise.
        """
        if not workspace.endswith("/"):
            workspace += "/"
        filepath = f"{workspace}{filename}"
        if os.path.isfile(filepath):
            return True
        return False

    def _get_absolute_filename(self, workspace: str, filename: str) -> str:
        """Constructs the absolute filename in cloud storage.

        Args:
            workspace (str): The workspace (prefix) path.
            filename (str): The name of the file.

        Return:
            str: The absolute filename in cloud storage.
        """
        protocol, _, path = self.endpoint.partition("://")
        absolute_filename = (
            f"{protocol}://{self.bucket_name}.{path}/{workspace}{filename}"
        )
        return absolute_filename

    def create_episode_workspace(self, episode_id: Optional[int]) -> str:
        """Creates a workspace (prefix) for an episode on the local filesystem.

        Args:
            episode_id (int | None): The ID of the episode.
        Returns:
            str: The prefix path for the episode workspace.
        """
        workspace_path = f"data/transcripts/episode_{episode_id:02d}/"
        try:
            os.makedirs(workspace_path, exist_ok=True)
        except Exception as e:
            raise RuntimeError(f"Error creating local workspace directory: {e}")
        # if episode_id is not None:
        #     return f"transcripts/episode_{episode_id}/"
        return workspace_path

    def save_file(self, workspace: str, filename: str, content) -> str:
        """Saves a file to the specified workspace in cloud storage.

        Args:
            workspace (str): The workspace (prefix) path.
            filename (str): The name of the file to save.
            content: The content to save text

        Returns:
            str: The full path of the saved file on local filesystem.
        """
        try:
            # Check if worspace name ends with /
            if not workspace.endswith("/"):
                workspace += "/"

            # Saving content to local file
            try:
                with open(f"{workspace}{filename}", "w") as file:
                    file.write(content)
            except Exception as e:
                raise RuntimeError(f"Error saving file to local storage: {e}")

            # Return absolute path
            return os.path.abspath(f"{workspace}{filename}")

        except Exception as e:
            raise e
