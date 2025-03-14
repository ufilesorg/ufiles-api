"""FastAPI server configuration."""

import dataclasses
import os
from pathlib import Path

from fastapi_mongo_base.core import config


@dataclasses.dataclass
class Settings(config.Settings):
    """Server config settings."""

    base_dir: str = Path(__file__).resolve().parent.parent
    base_path: str = ""

    update_time: int = 60 * 60 * 24

    S3_BUCKET_NAME: str = os.getenv("S3_BUCKET_NAME")
    S3_DOMAIN: str = os.getenv("S3_DOMAIN")
    S3_ENDPOINT: str = os.getenv("S3_ENDPOINT")
    S3_ACCESS_KEY: str = os.getenv("S3_ACCESS_KEY")
    S3_SECRET_KEY: str = os.getenv("S3_SECRET_KEY")
    S3_REGION: str = os.getenv("S3_REGION")

    ACCEPTED_FILE_TYPES = ["image/png", "image/jpeg", "image/jpg", "image/webp"]
