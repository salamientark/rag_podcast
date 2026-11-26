"""Tests for the S3-compatible cloud storage client (no network access)."""

from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError

from src.storage import cloud
from src.storage.cloud import CloudStorage

SUPABASE_ENDPOINT = "https://abcdefgh.storage.supabase.co/storage/v1/s3"
SPACES_ENDPOINT = "https://ams3.digitaloceanspaces.com"
KEY = "Le rendez-vous Tech/transcripts/episode_672/formatted_episode_672.txt"


def make_storage(
    monkeypatch: pytest.MonkeyPatch, endpoint: str, region: str | None = None
) -> CloudStorage:
    """Build a CloudStorage from a fake environment, bypassing any local .env."""
    monkeypatch.setattr(cloud, "load_dotenv", lambda: False)
    monkeypatch.setenv("BUCKET_ENDPOINT", endpoint)
    monkeypatch.setenv("BUCKET_KEY_ID", "test-key-id")
    monkeypatch.setenv("BUCKET_ACCESS_KEY", "test-access-key")
    monkeypatch.setenv("BUCKET_NAME", "podcasts")
    if region is None:
        monkeypatch.delenv("BUCKET_REGION", raising=False)
    else:
        monkeypatch.setenv("BUCKET_REGION", region)
    return CloudStorage()


@pytest.mark.parametrize("endpoint", [SUPABASE_ENDPOINT, SPACES_ENDPOINT])
def test_object_url_round_trips_to_key(monkeypatch, endpoint) -> None:
    storage = make_storage(monkeypatch, endpoint)
    url = storage.object_url(KEY)
    assert url == f"{endpoint}/podcasts/{KEY}"
    assert storage.key_from_url(url) == KEY


def test_object_url_ignores_trailing_slash_on_endpoint(monkeypatch) -> None:
    storage = make_storage(monkeypatch, SUPABASE_ENDPOINT + "/")
    assert storage.object_url(KEY) == f"{SUPABASE_ENDPOINT}/podcasts/{KEY}"


def test_key_from_legacy_virtual_hosted_url(monkeypatch) -> None:
    storage = make_storage(monkeypatch, SPACES_ENDPOINT)
    url = f"https://podcasts.ams3.digitaloceanspaces.com/{KEY}"
    assert storage.key_from_url(url) == KEY


def test_key_from_url_rejects_other_bucket(monkeypatch) -> None:
    storage = make_storage(monkeypatch, SUPABASE_ENDPOINT)
    with pytest.raises(ValueError, match="podcasts"):
        storage.key_from_url(f"{SUPABASE_ENDPOINT}/other-bucket/{KEY}")


@pytest.mark.parametrize(
    "url",
    [
        "https://elsewhere.example/podcasts/a.txt",
        f"{SUPABASE_ENDPOINT}/podcasts/",
        "data/Le rendez-vous Tech/transcripts/a.txt",
    ],
)
def test_key_from_url_rejects_foreign_or_empty(monkeypatch, url) -> None:
    storage = make_storage(monkeypatch, SUPABASE_ENDPOINT)
    with pytest.raises(ValueError):
        storage.key_from_url(url)


def test_key_from_url_keeps_special_characters(monkeypatch) -> None:
    storage = make_storage(monkeypatch, SUPABASE_ENDPOINT)
    key = "Quoi de neuf ? #1/podcasts/a b.txt"
    assert storage.key_from_url(storage.object_url(key)) == key


def test_get_absolute_filename_matches_object_url(monkeypatch) -> None:
    storage = make_storage(monkeypatch, SUPABASE_ENDPOINT)
    url = storage._get_absolute_filename("transcripts", "a.txt")
    assert url == storage.object_url("transcripts/a.txt")


def test_region_defaults_to_spaces_region(monkeypatch) -> None:
    storage = make_storage(monkeypatch, SPACES_ENDPOINT)
    assert storage.client.meta.region_name == "ams3"


def test_region_and_path_style_are_configurable(monkeypatch) -> None:
    storage = make_storage(monkeypatch, SUPABASE_ENDPOINT, region="eu-central-1")
    assert storage.client.meta.region_name == "eu-central-1"
    assert storage.client.meta.config.s3["addressing_style"] == "path"


def test_missing_bucket_name_is_rejected(monkeypatch) -> None:
    monkeypatch.setattr(cloud, "load_dotenv", lambda: False)
    monkeypatch.setenv("BUCKET_ENDPOINT", SUPABASE_ENDPOINT)
    monkeypatch.setenv("BUCKET_KEY_ID", "test-key-id")
    monkeypatch.setenv("BUCKET_ACCESS_KEY", "test-access-key")
    monkeypatch.delenv("BUCKET_NAME", raising=False)
    with pytest.raises(RuntimeError, match="BUCKET_NAME"):
        CloudStorage()


def test_object_exists(monkeypatch) -> None:
    storage = make_storage(monkeypatch, SUPABASE_ENDPOINT)
    storage.client = MagicMock()
    assert storage.object_exists(KEY) is True
    storage.client.head_object.assert_called_once_with(Bucket="podcasts", Key=KEY)

    not_found = ClientError({"Error": {"Code": "404"}}, "HeadObject")
    storage.client.head_object.side_effect = not_found
    assert storage.object_exists(KEY) is False

    denied = ClientError({"Error": {"Code": "403"}}, "HeadObject")
    storage.client.head_object.side_effect = denied
    with pytest.raises(ClientError):
        storage.object_exists(KEY)


def test_file_exist_joins_workspace_and_filename(monkeypatch) -> None:
    storage = make_storage(monkeypatch, SUPABASE_ENDPOINT)
    storage.client = MagicMock()
    assert storage.file_exist("transcripts", "a.txt") is True
    storage.client.head_object.assert_called_once_with(
        Bucket="podcasts", Key="transcripts/a.txt"
    )


def test_get_transcript_content_from_url_uses_object_key(monkeypatch) -> None:
    storage = make_storage(monkeypatch, SUPABASE_ENDPOINT)
    storage.client = MagicMock()
    storage.client.get_object.return_value = {
        "Body": MagicMock(read=lambda: "bonjour".encode())
    }
    monkeypatch.setattr(cloud, "get_cloud_storage", lambda: storage)

    content = CloudStorage.get_transcript_content_from_url(storage.object_url(KEY))

    assert content == "bonjour"
    storage.client.get_object.assert_called_once_with(Bucket="podcasts", Key=KEY)
