import os
from typing import Optional
from dotenv import load_dotenv

import boto3


class CloudStorage:
    """A client for interacting with cloud storage services. (DigitalOcean)"""


    def __init__(self):
        try:
            # Get credentials from environment variables
            load_dotenv()
            origin_endpoint = os.getenv("ORIGIN_ENDPOINT")
            key_id = os.getenv("SPACE_KEY_ID")
            access_key = os.getenv("SPACE_ACCESS_KEY")
            bucket_name = os.getenv("BUCKET_NAME")

            if not origin_endpoint or not key_id or not access_key:
                raise ValueError("Missing required environment variables for cloud storage client."
                                " Please ensure ORIGIN_ENDPOINT, SPACE_KEY_ID, and SPACE_ACCESS_KEY are set.")

            # Store bucket name
            self.bucket_name = bucket_name
            self.endpoint = origin_endpoint

            # Initialize the S3 client for DigitalOcean Spaces
            session = boto3.session.Session()
            self.client = session.client(
                's3',
                region_name='ams3',
                endpoint_url=origin_endpoint,
                aws_access_key_id=key_id,
                aws_secret_access_key=access_key
            )

        except ValueError as e:
            raise RuntimeError(f"Error loading environment variables: {e}")

    def get_client(self):
        """Returns the initialized cloud storage client."""
        return self.client

    def _get_absolute_filename(self, workspace: str, filename: str) -> str:
        """Constructs the absolute filename in cloud storage.

        Args:
            workspace (str): The workspace (prefix) path.
            filename (str): The name of the file.

        Return:
            str: The absolute filename in cloud storage.
        """
        protocol, _, path = self.endpoint.partition("://")
        absolute_filename = f"{protocol}://{self.bucket_name}.{path}/{workspace}{filename}"
        return absolute_filename
        

    def create_episode_workspace(self, episode_id: Optional[int]) -> str:
        """Creates a workspace (prefix) for an episode in the cloud storage.
        Args:
            episode_id (int | None): The ID of the episode.
        Returns:
            str: The prefix path for the episode workspace.
        """
        return "transcripts/"

    def save_file(self, workspace: str, filename: str, content) -> str:
        """Saves a file to the specified workspace in cloud storage.

        Args:
            workspace (str): The workspace (prefix) path.
            filename (str): The name of the file to save.
            content: The content to upload (file-like object or bytes).

        Returns:
            str: The full path of the saved file in cloud storage.
        """
        try:
            # Check if worspace name ends with /
            if not workspace.endswith("/"):
                workspace += "/"

            # Create temporary dir to save file
            try:
                os.makedirs("proc", exist_ok=True)
                temp_filename = f"proc/{filename}"
                with open(temp_filename, "w") as temp_file:
                    temp_file.write(content)
            except Exception as e:
                raise RuntimeError(f"Error creating temporary file: {e}")

            # Upload the file to cloud storage
            self.client.upload_file(temp_filename, self.bucket_name, f"{workspace}{filename}")

            # Remove temporary file and dir
            try:
                os.remove(temp_filename)
                os.rmdir("proc")
            except Exception as e:
                print(f"Warning: Failed to clean up temporary files: {e}")

            # Return URL instead of path
            return self._get_absolute_filename(workspace, filename)

        except Exception as e:
            if os.path.exists(temp_filename):
                os.remove(temp_filename)
                os.rmdir("proc")
            raise RuntimeError(f"Error saving file to cloud storage: {e}")


class LocalStorage:
    """A client for interacting with cloud storage services. (DigitalOcean)"""


    def _get_absolute_filename(self, workspace: str, filename: str) -> str:
        """Constructs the absolute filename in cloud storage.

        Args:
            workspace (str): The workspace (prefix) path.
            filename (str): The name of the file.

        Return:
            str: The absolute filename in cloud storage.
        """
        protocol, _, path = self.endpoint.partition("://")
        absolute_filename = f"{protocol}://{self.bucket_name}.{path}/{workspace}{filename}"
        return absolute_filename

    def check_file_existance(self, workspace: str, filename: str) -> bool:
        """
        Check if a file exists in cloud storage.

        Args:
            workspace (str): The workspace (prefix) path.
            filename (str): The name of the file.

        Returns:
            bool: True if the file exists, False otherwise.
        """
        if not workspace.endswith("/"):
            workspace += "/"
        try:
            self.client.head_object(Bucket=self.bucket_name, Key=f"{workspace}{filename}")
            return True
        except self.client.exceptions.NoSuchKey:
            return False
        except Exception as e:
            raise RuntimeError(f"Error checking file existence in cloud storage: {e}")
        

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

