import os
from typing import Optional
from dotenv import load_dotenv
from functools import lru_cache

import boto3
from botocore.exceptions import ClientError
from .base import BaseStorage


class CloudStorage(BaseStorage):
    """A client for interacting with cloud storage services. (DigitalOcean)"""

    def __init__(self):
        try:
            # Get credentials from environment variables
            load_dotenv()
            origin_endpoint = os.getenv("BUCKET_ENDPOINT")
            key_id = os.getenv("BUCKET_KEY_ID")
            access_key = os.getenv("BUCKET_ACCESS_KEY")
            bucket_name = os.getenv("BUCKET_NAME")

            if not origin_endpoint or not key_id or not access_key:
                raise ValueError(
                    "Missing required environment variables for cloud storage client."
                    " Please ensure BUCKET_ENDPOINT, BUCKET_KEY_ID, and BUCKET_ACCESS_KEY are set."
                )

            # Store bucket name
            self.bucket_name = bucket_name
            self.endpoint = origin_endpoint

            # Initialize the S3 client for DigitalOcean Spaces
            session = boto3.session.Session()
            self.client = session.client(
                "s3",
                region_name="ams3",
                endpoint_url=origin_endpoint,
                aws_access_key_id=key_id,
                aws_secret_access_key=access_key,
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
        absolute_filename = (
            f"{protocol}://{self.bucket_name}.{path}/{workspace}{filename}"
        )
        return absolute_filename

    def file_exist(self, workspace: str, filename: str) -> bool:
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
            self.client.head_object(
                Bucket=self.bucket_name, Key=f"{workspace}{filename}"
            )
        except ClientError as e:
            # head_object returns "404" as string, not NoSuchKey
            # See: https://github.com/boto/boto3/issues/2442
            error_code = str(e.response.get("Error", {}).get("Code", ""))
            if error_code in ("404", "NoSuchKey"):
                return False
            raise  # Re-raise other errors (403 AccessDenied, 500, etc.)
        return True

    def create_episode_workspace(self, episode_id: Optional[int]) -> str:
        """
        Create a workspace prefix for an episode in cloud storage.

        Note: This implementation returns a static prefix and does not actually
        create any cloud resources. The episode_id parameter is ignored.

        Parameters:
            episode_id (Optional[int]): Episode identifier (ignored by this implementation).

        Returns:
            str: The workspace prefix "transcripts/".
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
        temp_filename = None
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
            self.client.upload_file(
                temp_filename, self.bucket_name, f"{workspace}{filename}"
            )

            # Remove temporary file and dir
            try:
                os.remove(temp_filename)
                os.rmdir("proc")
            except Exception as e:
                print(f"Warning: Failed to clean up temporary files: {e}")

            # Return URL instead of path
            return self._get_absolute_filename(workspace, filename)

        except Exception as e:
            if temp_filename and os.path.exists(temp_filename):
                os.remove(temp_filename)
                try:
                    os.rmdir("proc")
                except OSError:
                    pass  # Directory not empty or doesn't exist
            raise RuntimeError(f"Error saving file to cloud storage: {e}")


@lru_cache(maxsize=1)
def get_cloud_storage() -> CloudStorage:
    """
    Get a cached instance of CloudStorage.
    Returns:
        CloudStorage: An instance of CloudStorage.
    """
    return CloudStorage()
