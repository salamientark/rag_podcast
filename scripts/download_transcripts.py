import argparse
import os
import sys
import tempfile
from pathlib import Path
from typing import Iterable

from dotenv import load_dotenv
import boto3
from botocore.exceptions import ClientError


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Download transcript files from an S3-compatible bucket and bundle them into a zip."
        )
    )
    parser.add_argument(
        "--prefix",
        help=(
            "Optional key prefix to scope the search "
            "(e.g. 'Le rendez-vous Jeux - RDV Jeux/')."
        ),
    )
    parser.add_argument(
        "--output",
        default="transcripts_bundle.zip",
        help="Zip file path to write (default: transcripts_bundle.zip).",
    )
    parser.add_argument(
        "--region",
        default=os.getenv("BUCKET_REGION", "ams3"),
        help="S3 region name (default: BUCKET_REGION or ams3).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List matching transcript keys without downloading.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Disable transcript-only filtering and include all keys under the prefix.",
    )
    return parser.parse_args()


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


def is_transcript_key(key: str) -> bool:
    return key.startswith("transcripts/") or "/transcripts/" in key


def iter_keys(client, bucket: str, prefix: str | None) -> Iterable[str]:
    continuation = None
    while True:
        params = {"Bucket": bucket}
        if prefix:
            params["Prefix"] = prefix
        if continuation:
            params["ContinuationToken"] = continuation
        response = client.list_objects_v2(**params)
        for obj in response.get("Contents", []):
            key = obj.get("Key")
            if not key or key.endswith("/"):
                continue
            yield key
        if not response.get("IsTruncated"):
            break
        continuation = response.get("NextContinuationToken")


def main() -> int:
    load_dotenv()
    args = parse_args()

    try:
        endpoint = require_env("BUCKET_ENDPOINT")
        key_id = require_env("BUCKET_KEY_ID")
        access_key = require_env("BUCKET_ACCESS_KEY")
        bucket_name = require_env("BUCKET_NAME")
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    output_path = Path(args.output)
    if output_path.exists():
        print(
            f"Error: output file already exists: {output_path}",
            file=sys.stderr,
        )
        return 1

    session = boto3.session.Session()
    client = session.client(
        "s3",
        region_name=args.region,
        endpoint_url=endpoint,
        aws_access_key_id=key_id,
        aws_secret_access_key=access_key,
    )

    matching_keys = []
    for key in iter_keys(client, bucket_name, args.prefix):
        if args.all or is_transcript_key(key):
            matching_keys.append(key)

    if not matching_keys:
        print("No transcript files found with the given filter.", file=sys.stderr)
        return 1

    if args.dry_run:
        print("\n".join(matching_keys))
        print(f"\nFound {len(matching_keys)} file(s).")
        return 0

    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            for key in matching_keys:
                local_path = tmp_root / key
                local_path.parent.mkdir(parents=True, exist_ok=True)
                client.download_file(bucket_name, key, str(local_path))

            import zipfile

            with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for local_file in tmp_root.rglob("*"):
                    if local_file.is_file():
                        zf.write(local_file, local_file.relative_to(tmp_root))
    except ClientError as exc:
        print(f"Download failed: {exc}", file=sys.stderr)
        return 1

    print(f"Archived {len(matching_keys)} file(s) to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
