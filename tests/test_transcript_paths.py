"""Tests for resolving an episode transcript to a local file (no network access)."""

from pathlib import Path

import pytest

from src.pipeline import transcript_paths
from src.pipeline.transcript_paths import resolve_local_transcript

URL = (
    "https://abcdefgh.storage.supabase.co/storage/v1/s3/podcasts/"
    "Le rendez-vous Tech/transcripts/episode_042/formatted_episode_042.txt"
)
LOCAL = Path(
    "data/Le rendez-vous Tech/transcripts/episode_042/formatted_episode_042.txt"
)


def make_episode(transcript_path: str | None) -> dict:
    return {
        "podcast": "Le rendez-vous Tech",
        "episode_id": 42,
        "formatted_transcript_path": transcript_path,
    }


@pytest.fixture(autouse=True)
def in_tmp_dir(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)


def forbid_download(monkeypatch) -> None:
    def fail(url: str) -> str:
        raise AssertionError(f"unexpected download of {url}")

    monkeypatch.setattr(transcript_paths, "_download_transcript", fail)


@pytest.mark.parametrize("missing", [None, ""])
def test_missing_transcript_path_returns_none(monkeypatch, missing) -> None:
    forbid_download(monkeypatch)
    assert resolve_local_transcript(make_episode(missing)) is None


def test_local_path_is_returned_unchanged(monkeypatch) -> None:
    forbid_download(monkeypatch)
    path = "data/Le rendez-vous Tech/transcripts/episode_042/custom.txt"
    assert resolve_local_transcript(make_episode(path)) == Path(path)


def test_url_uses_existing_local_copy(monkeypatch) -> None:
    forbid_download(monkeypatch)
    LOCAL.parent.mkdir(parents=True)
    LOCAL.write_text("déjà là", encoding="utf-8")
    assert resolve_local_transcript(make_episode(URL)) == LOCAL
    assert LOCAL.read_text(encoding="utf-8") == "déjà là"


def test_url_without_local_copy_is_downloaded(monkeypatch) -> None:
    calls = []

    def fake_download(url: str) -> str:
        calls.append(url)
        return "bonjour é"

    monkeypatch.setattr(transcript_paths, "_download_transcript", fake_download)

    assert resolve_local_transcript(make_episode(URL)) == LOCAL
    assert calls == [URL]
    assert LOCAL.read_text(encoding="utf-8") == "bonjour é"


def test_empty_local_copy_is_downloaded_again(monkeypatch) -> None:
    monkeypatch.setattr(transcript_paths, "_download_transcript", lambda url: "texte")
    LOCAL.parent.mkdir(parents=True)
    LOCAL.write_text("", encoding="utf-8")
    assert resolve_local_transcript(make_episode(URL)) == LOCAL
    assert LOCAL.read_text(encoding="utf-8") == "texte"


def test_failed_download_leaves_no_file(monkeypatch) -> None:
    def fail(url: str) -> str:
        raise RuntimeError("bucket unreachable")

    monkeypatch.setattr(transcript_paths, "_download_transcript", fail)

    with pytest.raises(RuntimeError, match="bucket unreachable"):
        resolve_local_transcript(make_episode(URL))
    assert not LOCAL.exists()
    assert not list(Path("data").rglob("*.tmp"))
