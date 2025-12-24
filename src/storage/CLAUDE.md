# Storage Module

## Purpose

Provides an abstraction layer for file storage operations, supporting both local filesystem and cloud storage (DigitalOcean Spaces via S3-compatible API).

This module is a dependency for pipeline stages that need to write transcripts and other artifacts without hardcoding storage backends.

## Architecture

### Base Class

- **`BaseStorage`** (`base.py`): Abstract base class defining the storage interface

### Implementations

#### LocalStorage (`local.py`)

- Creates workspace directories under `data/transcripts/episode_{id:03d}/` (current implementation)
- Writes files to local filesystem
- Returns absolute file paths

#### CloudStorage (`cloud.py`)

- Uses boto3 S3 client with custom endpoint
- Uses temporary files in `proc/` directory for uploads
- Returns public URLs instead of paths
- Workspace is currently static `transcripts/` (episode_id ignored)

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

## Review-Grade Rules / Contracts

1. **LocalStorage must not depend on cloud attributes**. It should not reference `endpoint` or `bucket_name`.
2. **Return type differences are intentional**:
   - Local returns filesystem paths
   - Cloud returns URLs
     Callers must treat these as opaque strings and not assume local path semantics.
3. **Workspace normalization**: implementations should consistently handle trailing `/` in `workspace`.
4. **Cloud temp file cleanup**: failures should not leave `proc/` artifacts behind.

## Gotchas (current code reality)

1. **Inconsistent docstrings**: LocalStorage docstring incorrectly says "cloud storage".
2. **LocalStorage.\_get_absolute_filename is incorrect**: references undefined `self.endpoint` and `self.bucket_name`. Any call to this method will fail.
3. **Cloud workspace ignores episode_id**: always returns `transcripts/` regardless of parameter.
4. **CloudStorage.file_exist() error semantics**: non-404 errors should not be treated as “file exists”. Reviews should ensure correct boolean behavior.

## Usage Example

```python
from src.storage import LocalStorage, CloudStorage

# Local development
storage = LocalStorage()
workspace = storage.create_episode_workspace(1)  # "data/transcripts/episode_001/"
path = storage.save_file(workspace, "transcript.txt", "content")

# Production (cloud)
storage = CloudStorage()
workspace = storage.create_episode_workspace(1)  # "transcripts/"
url = storage.save_file(workspace, "transcript.txt", "content")
```
