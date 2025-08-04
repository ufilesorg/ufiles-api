"""FastAPI server configuration."""

import dataclasses
import os
from pathlib import Path
from typing import ClassVar

from fastapi_mongo_base.core import config


@dataclasses.dataclass
class Settings(config.Settings):
    """Server config settings."""

    base_dir: str = Path(__file__).resolve().parent.parent
    base_path: str = "/api/media/v1"

    update_time: int = 60 * 60 * 24

    # Storage backend configuration
    STORAGE_BACKEND: str = os.getenv("STORAGE_BACKEND", "s3")  # s3, local, nextcloud

    # S3 Storage Configuration
    S3_BUCKET_NAME: str = os.getenv("S3_BUCKET_NAME")
    S3_DOMAIN: str | None = os.getenv("S3_DOMAIN")
    S3_ENDPOINT: str = os.getenv("S3_ENDPOINT")
    S3_ACCESS_KEY: str = os.getenv("S3_ACCESS_KEY")
    S3_SECRET_KEY: str = os.getenv("S3_SECRET_KEY")
    S3_REGION: str | None = os.getenv("S3_REGION")

    # Local Storage Configuration
    LOCAL_STORAGE_PATH: str = os.getenv("LOCAL_STORAGE_PATH", "./storage")
    LOCAL_STORAGE_BASE_URL: str = os.getenv("LOCAL_STORAGE_BASE_URL")

    # NextCloud/OwnCloud Configuration
    NEXTCLOUD_BASE_URL: str = os.getenv("NEXTCLOUD_BASE_URL")
    NEXTCLOUD_USERNAME: str = os.getenv("NEXTCLOUD_USERNAME")
    NEXTCLOUD_PASSWORD: str = os.getenv("NEXTCLOUD_PASSWORD")
    NEXTCLOUD_WEBDAV_PATH: str = os.getenv("NEXTCLOUD_WEBDAV_PATH", "/apps/files")

    accepted_file_types: ClassVar[list[str]] = [
        "image/png",
        "image/jpeg",
        "image/jpg",
        "image/webp",
    ]
    size_limits: int = 0
    pubilc_access_type: bool = True

    @property
    def storage_config(self) -> dict[str, str]:
        """Get storage configuration based on selected backend."""
        backend = self.STORAGE_BACKEND.lower()

        if backend == "s3":
            return {
                "aws_access_key_id": self.S3_ACCESS_KEY,
                "aws_secret_access_key": self.S3_SECRET_KEY,
                "region_name": self.S3_REGION,
                "endpoint_url": self.S3_ENDPOINT,
                "bucket_name": self.S3_BUCKET_NAME,
                "domain": self.S3_DOMAIN,
            }
        elif backend == "local":
            return {
                "base_path": self.LOCAL_STORAGE_PATH,
                "base_url": self.LOCAL_STORAGE_BASE_URL,
                "create_dirs": True,
            }
        elif backend in ("nextcloud", "owncloud"):
            return {
                "base_url": self.NEXTCLOUD_BASE_URL,
                "username": self.NEXTCLOUD_USERNAME,
                "password": self.NEXTCLOUD_PASSWORD,
                "webdav_path": self.NEXTCLOUD_WEBDAV_PATH,
            }
        else:
            raise ValueError(f"Unsupported storage backend: {backend}")

    @classmethod
    def get_log_config(cls, console_level: str = "INFO", **kwargs: object) -> dict:
        log_config = {
            "formatters": {
                "standard": {
                    "format": "[{levelname} : {filename}:{lineno} : {asctime} -> {funcName:10}] {message}",  # noqa: E501
                    "style": "{",
                }
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "level": console_level,
                    "formatter": "standard",
                },
                "file": {
                    "class": "logging.FileHandler",
                    "level": "INFO",
                    "formatter": "standard",
                    "filename": "logs/app.log",
                },
            },
            "loggers": {
                "": {
                    "handlers": [
                        "console",
                        "file",
                    ],
                    "level": "INFO",
                    "propagate": True,
                },
            },
            "version": 1,
        }
        return log_config
