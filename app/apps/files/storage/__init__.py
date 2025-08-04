"""Storage backends for file management."""

from .base_storage import StorageBackend
from .local_storage import LocalStorageBackend

try:
    from .nextcloud_storage import NextCloudStorageBackend
except ImportError:
    NextCloudStorageBackend = None

try:
    from .s3_storage import S3StorageBackend
except ImportError:
    S3StorageBackend = None

__all__ = (
    [
        "LocalStorageBackend",
        "StorageBackend",
    ]
    + (["NextCloudStorageBackend"] if NextCloudStorageBackend else [])
    + (["S3StorageBackend"] if S3StorageBackend else [])
)
