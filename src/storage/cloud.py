import os
from typing import Optional
from urllib.parse import urlparse
from logging import getLogger
from dotenv import load_dotenv
from functools import lru_cache

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from .base import BaseStorage

logger = getLogger(__name__)

# Kept for existing DigitalOcean Spaces setups; override with BUCKET_REGION.
DEFAULT_BUCKET_REGION = "ams3"


class CloudStorage(BaseStorage):
    """A client for any S3-compatible object store.

    Works with DigitalOcean Spaces, Supabase Storage, Cloudflare R2 and others.
    Objects are identified by path-style URLs, `{endpoint}/{bucket}/{key}`, which
    are stored in the database and resolved back to keys with `key_from_url`.
    They are identifiers for this client, not necessarily public HTTP links.
    """

    def __init__(self):
        try:
            # Get credentials from environment variables
            load_dotenv()
            origin_endpoint = os.getenv("BUCKET_ENDPOINT")
            key_id = os.getenv("BUCKET_KEY_ID")
            access_key = os.getenv("BUCKET_ACCESS_KEY")
            bucket_name = os.getenv("BUCKET_NAME")

            if not origin_endpoint or not key_id or not access_key or not bucket_name:
                raise ValueError(
                    "Missing required environment variables for cloud storage client."
                    " Please ensure BUCKET_ENDPOINT, BUCKET_KEY_ID, BUCKET_ACCESS_KEY"
                    " and BUCKET_NAME are set."
                )
            region = os.getenv("BUCKET_REGION", "").strip() or DEFAULT_BUCKET_REGION

            # Store bucket name
            self.bucket_name = bucket_name
            self.endpoint = origin_endpoint.rstrip("/")

            # Path-style addressing works on every S3-compatible provider,
            # including those whose endpoint has a path (Supabase Storage).
            session = boto3.session.Session()
            self.client = session.client(
                "s3",
                region_name=region,
                endpoint_url=self.endpoint,
                aws_access_key_id=key_id,
                aws_secret_access_key=access_key,
                config=Config(s3={"addressing_style": "path"}),
            )

        except ValueError as e:
            raise RuntimeError(f"Error loading environment variables: {e}")

    def get_client(self):
        """Returns the initialized cloud storage client."""
        return self.client

    @staticmethod
    def get_transcript_content_from_url(transcript_url: str) -> str:
        """
        Fetch transcript content from the given URL.

        Parameters:
            transcript_url (str): The URL of the transcript.

        Returns:
            str: The content of the transcript.
        """
        try:
            # Get Client
            storage_engine = get_cloud_storage()
            client = storage_engine.get_client()

            key = storage_engine.key_from_url(transcript_url)
            response = client.get_object(Bucket=storage_engine.bucket_name, Key=key)
            return response["Body"].read().decode()
        except Exception as exc:
            logger.error(
                f"[get_transcript_content] Error during transcript fetch: {exc}",
                exc_info=True,
            )
            raise

    def _get_absolute_filename(self, workspace: str, filename: str) -> str:
        """Constructs the absolute filename in cloud storage.

        Args:
            workspace (str): The workspace (prefix) path.
            filename (str): The name of the file.

        Return:
            str: The absolute filename in cloud storage.
        """
        if not workspace.endswith("/"):
            workspace += "/"
        return self.object_url(f"{workspace}{filename}")

    def object_url(self, key: str) -> str:
        """Build the URL that identifies an object of the configured bucket.

        Args:
            key (str): The object key inside the bucket.

        Returns:
            str: A path-style URL, `{endpoint}/{bucket}/{key}`.
        """
        return f"{self.endpoint}/{self.bucket_name}/{key.lstrip('/')}"

    def key_from_url(self, url: str) -> str:
        """Extract the object key from a URL built for the configured bucket.

        Accepts the path-style URLs produced by `object_url` and the legacy
        virtual-hosted form, `https://{bucket}.{endpoint host}/{key}`.

        Args:
            url (str): The object URL, as stored in the database.

        Returns:
            str: The object key inside the bucket.

        Raises:
            ValueError: If the URL does not point into the configured bucket.
        """
        # Prefixes are matched on the raw string: keys are stored unencoded and
        # may contain characters ("?", "#") that URL parsing would cut off.
        endpoint = urlparse(self.endpoint)
        prefixes = (
            f"{self.endpoint}/{self.bucket_name}/",
            f"{endpoint.scheme}://{self.bucket_name}.{endpoint.netloc}/",
        )
        for prefix in prefixes:
            if url.startswith(prefix) and len(url) > len(prefix):
                return url[len(prefix) :]
        raise ValueError(f"URL does not belong to bucket '{self.bucket_name}': {url}")

    def object_exists(self, key: str) -> bool:
        """Check if an object exists in the configured bucket.

        Args:
            key (str): The object key inside the bucket.

        Returns:
            bool: True if the object exists, False otherwise.

        Raises:
            ClientError: For any error other than "not found" (403, 500, ...).
        """
        try:
            self.client.head_object(Bucket=self.bucket_name, Key=key)
        except ClientError as e:
            # head_object returns "404" as string, not NoSuchKey
            # See: https://github.com/boto/boto3/issues/2442
            error_code = str(e.response.get("Error", {}).get("Code", ""))
            if error_code in ("404", "NoSuchKey", "NotFound"):
                return False
            raise  # Re-raise other errors (403 AccessDenied, 500, etc.)
        return True

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
        return self.object_exists(f"{workspace}{filename}")

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
