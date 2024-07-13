from enum import Enum

from apps.base.models import OwnedEntity
from pydantic import BaseModel, model_validator
from pymongo import ASCENDING, IndexModel
from server.config import Settings


class AccessType(str, Enum):
    public = "public"
    stream = "stream"
    encoded = "encoded"
    singed = "signed"


class S3Config(BaseModel):
    s3_endpoint: str
    s3_access_key: str
    s3_secret_key: str
    s3_region: str | None = None
    s3_bucket_name: str | None = None
    s3_domain: str | None = None


class Config(BaseModel):
    s3: S3Config | None = None

    access_type: AccessType = AccessType.public

    accepted_file_types: list[str] = [
        "image/png",
        "image/jpeg",
        "image/jpg",
        "image/webp",
    ]
    size_limits: int = 100 * 1024 * 1024


class Business(OwnedEntity):
    name: str
    description: str | None = None
    domain: str
    config: Config

    class Settings:
        indexes = [
            IndexModel([("name", ASCENDING)], unique=True),
            IndexModel([("domain", ASCENDING)], unique=True),
        ]

    @classmethod
    async def get_by_origin(cls, origin: str):
        return await cls.find_one(cls.domain == origin)

    @model_validator(mode="before")
    def validate_domain(data: dict):
        if not data.get("domain"):
            business_name_domain = f"{data.get('name')}.{Settings.root_url}"
            data["domain"] = business_name_domain

        return data
