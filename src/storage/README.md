# Storage Module

Unified storage abstraction for handling local and cloud storage operations in the podcast RAG system.

## Overview

The storage module provides a consistent interface for file operations across different storage backends:
- **Local Storage** - Filesystem-based storage for development and testing
- **Cloud Storage** - S3-compatible storage (DigitalOcean Spaces) for production

## Architecture

```
src/storage/
├── __init__.py      # Package exports
├── base.py          # Abstract storage interface
├── local.py         # Local filesystem implementation
└── cloud.py         # Cloud storage implementation (S3-compatible)
```

### Class Hierarchy
```python
BaseStorage (ABC)
├── LocalStorage      # Local filesystem backend
└── CloudStorage      # S3-compatible cloud backend
```

## Quick Start

### Local Storage (Development)
```python
from src.storage import LocalStorage

# Initialize local storage
storage = LocalStorage()

# Create workspace for episode
workspace = storage.create_episode_workspace(671)
# Returns: "data/transcripts/episode_671/"

# Check if file exists
exists = storage.file_exist(workspace, "transcript.txt")

# Save file content
file_path = storage.save_file(
    workspace, 
    "formatted_episode_671.txt", 
    "Episode content here..."
)
# Returns: "/full/path/to/data/transcripts/episode_671/formatted_episode_671.txt"
```

### Cloud Storage (Production)
```python
from src.storage import CloudStorage

# Initialize cloud storage (requires environment variables)
storage = CloudStorage()

# Create workspace for episode
workspace = storage.create_episode_workspace(671)
# Returns: "transcripts/"

# Check if file exists in cloud
exists = storage.file_exist(workspace, "transcript.txt")

# Save file to cloud storage
file_url = storage.save_file(
    workspace,
    "formatted_episode_671.txt", 
    "Episode content here..."
)
# Returns: "https://bucket.endpoint.com/transcripts/formatted_episode_671.txt"
```

## Configuration

### Local Storage
No configuration required - uses local filesystem with `data/transcripts/` directory structure.

### Cloud Storage
Requires S3-compatible service credentials:

```bash
# Required environment variables
BUCKET_ENDPOINT=https://ams3.digitaloceanspaces.com    # S3 endpoint URL
BUCKET_KEY_ID=your_access_key_id                       # Access key ID
BUCKET_ACCESS_KEY=your_secret_access_key               # Secret access key
BUCKET_NAME=your_bucket_name                           # Bucket/container name
```

Add to `.env` file:
```bash
BUCKET_ENDPOINT=https://ams3.digitaloceanspaces.com
BUCKET_KEY_ID=DO00ABC123DEF456789
BUCKET_ACCESS_KEY=xyz789abc123def456ghi789jkl012mno345pqr678
BUCKET_NAME=podcast-storage
```

## Storage Interface

All storage implementations provide the same interface defined in `BaseStorage`:

### Methods

#### `file_exist(workspace: str, filename: str) -> bool`
Check if a file exists in the storage backend.

#### `create_episode_workspace(episode_id: Optional[int]) -> str`
Create a workspace/directory for episode files and return the path/prefix.

#### `save_file(workspace: str, filename: str, content: str) -> str`
Save content to a file and return the full path or URL.

#### `_get_absolute_filename(workspace: str, filename: str) -> str`
Construct the absolute path/URL for a file (implementation-specific).

## Usage Patterns

### Episode Processing Pipeline
```python
# Storage-agnostic episode processing
def process_episode(episode_id: int, storage: BaseStorage, content: str):
    # Create workspace
    workspace = storage.create_episode_workspace(episode_id)
    
    # Check if already processed
    if storage.file_exist(workspace, f"processed_{episode_id}.txt"):
        print(f"Episode {episode_id} already processed")
        return
    
    # Save processed content
    result_path = storage.save_file(
        workspace, 
        f"processed_{episode_id}.txt",
        content
    )
    
    print(f"Saved to: {result_path}")

# Use with local storage
local_storage = LocalStorage()
process_episode(671, local_storage, "Content...")

# Use with cloud storage  
cloud_storage = CloudStorage()
process_episode(671, cloud_storage, "Content...")
```

### Storage Factory Pattern
```python
import os
from src.storage import LocalStorage, CloudStorage

def get_storage():
    """Factory function to get appropriate storage backend."""
    if os.getenv("USE_CLOUD_STORAGE", "false").lower() == "true":
        return CloudStorage()
    return LocalStorage()

# Use in your application
storage = get_storage()
workspace = storage.create_episode_workspace(672)
```

## File Organization

### Local Storage Structure
```
data/
└── transcripts/
    ├── episode_671/
    │   ├── raw_transcript.txt
    │   ├── formatted_episode_671.txt
    │   └── chunks.json
    ├── episode_672/
    │   └── formatted_episode_672.txt
    └── episode_673/
        └── formatted_episode_673.txt
```

### Cloud Storage Structure
```
bucket-name/
└── transcripts/
    ├── raw_transcript_671.txt
    ├── formatted_episode_671.txt
    ├── formatted_episode_672.txt
    ├── chunks_671.json
    └── chunks_672.json
```

## Provider Support

### Supported Cloud Providers
- **DigitalOcean Spaces** (default configuration)
- **Amazon S3** (change endpoint and region)
- **MinIO** (self-hosted S3-compatible)
- **Wasabi** (S3-compatible cloud storage)

### Provider Configuration Examples

#### Amazon S3
```bash
BUCKET_ENDPOINT=https://s3.us-west-2.amazonaws.com
BUCKET_KEY_ID=AKIA...
BUCKET_ACCESS_KEY=...
BUCKET_NAME=my-podcast-bucket
```

#### MinIO (Self-hosted)
```bash
BUCKET_ENDPOINT=http://localhost:9000
BUCKET_KEY_ID=minioadmin
BUCKET_ACCESS_KEY=minioadmin
BUCKET_NAME=podcasts
```

## Error Handling

All storage operations raise `RuntimeError` on failure:

```python
try:
    storage = CloudStorage()
    workspace = storage.create_episode_workspace(671)
    result = storage.save_file(workspace, "test.txt", "content")
except RuntimeError as e:
    print(f"Storage operation failed: {e}")
```

Common error scenarios:
- **Missing credentials** - CloudStorage initialization fails
- **Network issues** - Cloud operations timeout
- **Permission errors** - Local filesystem access denied
- **Disk space** - Local storage full

## Testing

### Unit Tests
```python
import unittest
from src.storage import LocalStorage, CloudStorage

class TestStorage(unittest.TestCase):
    def test_local_storage(self):
        storage = LocalStorage()
        workspace = storage.create_episode_workspace(999)
        
        # Test save and exist
        result = storage.save_file(workspace, "test.txt", "content")
        self.assertTrue(storage.file_exist(workspace, "test.txt"))
```

### Integration Tests
See `upload_test_file.py` and `download_file_test.py` for cloud storage integration examples.

## Performance Considerations

### Local Storage
- **Pros**: Fast, no network latency, no bandwidth costs
- **Cons**: Limited to single machine, no automatic backup
- **Best for**: Development, testing, small deployments

### Cloud Storage  
- **Pros**: Scalable, durable, accessible from multiple machines
- **Cons**: Network latency, bandwidth costs, requires credentials
- **Best for**: Production, distributed systems, backup storage

### Optimization Tips
- Use local storage for development to speed up iteration
- Batch upload operations when possible for cloud storage
- Consider file compression for large transcripts
- Implement retry logic for network operations

## Security

### Local Storage
- File permissions managed by OS
- No network exposure
- Backup responsibility on user

### Cloud Storage
- Credentials must be kept secure
- Use IAM policies to limit access scope
- Enable bucket versioning for data protection
- Consider encryption at rest and in transit

### Best Practices
- Never commit credentials to version control
- Use environment variables for configuration
- Rotate access keys regularly
- Monitor storage access logs
- Implement least-privilege access policies