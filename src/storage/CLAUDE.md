# Storage Module

## Purpose

Provides an abstraction layer for file storage operations, supporting both local filesystem and cloud storage (DigitalOcean Spaces via S3-compatible API).

## Architecture

### Base Class

- **`BaseStorage`** (`base.py`): Abstract base class defining the storage interface

### Implementations

#### LocalStorage (`local.py`)

- Creates workspace directories under `data/transcripts/episode_{id:03d}/`
- Returns absolute file paths
- Auto-creates directories with `os.makedirs(exist_ok=True)`

#### CloudStorage (`cloud.py`)

- Uses boto3 S3 client with custom endpoint
- Uses temporary files in `proc/` directory for uploads
- Returns public URLs instead of paths
- Workspace is always `transcripts/` (episode_id not used)

## Core Methods

### `create_episode_workspace(episode_id: Optional[int]) -> str`

- **Local**: Creates `data/transcripts/episode_{id:03d}/`
- **Cloud**: Returns static `transcripts/`

### `save_file(workspace: str, filename: str, content: str) -> str`

- **Local**: Writes to filesystem, returns absolute path
- **Cloud**: Creates temp file, uploads to S3, returns URL

### `file_exist(workspace: str, filename: str) -> bool`

- **Local**: Uses `os.path.isfile()`
- **Cloud**: Uses S3 `head_object()` with error handling

## Environment Variables (CloudStorage)

```
BUCKET_ENDPOINT=https://...
BUCKET_KEY_ID=your_key_id
BUCKET_ACCESS_KEY=your_secret_key
BUCKET_NAME=your_bucket_name
```

## Gotchas

1. **Inconsistent Docstrings**: LocalStorage docstring incorrectly says "cloud storage".

2. **LocalStorage.\_get_absolute_filename**: References undefined `self.endpoint` and `self.bucket_name`. Will fail if called.

3. **Cloud Workspace Ignores episode_id**: Always returns `transcripts/` regardless of parameter.

4. **Temporary File Management**: `proc/` directory created for temp files. Cleanup may leave artifacts on failure.

5. **Return Type Differences**: LocalStorage returns paths, CloudStorage returns URLs.

6. **No Async Support**: All operations synchronous.

7. **Hard-coded Region**: CloudStorage uses `ams3` (Amsterdam datacenter).

## Usage Example

```python
from storage import LocalStorage, CloudStorage

# Local development
storage = LocalStorage()
workspace = storage.create_episode_workspace(1)  # "data/transcripts/episode_001/"
path = storage.save_file(workspace, "transcript.txt", "content")

# Production (cloud)
storage = CloudStorage()
workspace = storage.create_episode_workspace(1)  # "transcripts/"
url = storage.save_file(workspace, "transcript.txt", "content")
```
