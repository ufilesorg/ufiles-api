import json
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
    endpoint: str
    access_key: str
    secret_key: str
    region: str | None = None
    bucket_name: str | None = None
    domain: str | None = None

    @classmethod
    def defaults(cls):
        return cls(
            access_key=Settings.S3_ACCESS_KEY,
            secret_key=Settings.S3_SECRET_KEY,
            endpoint=Settings.S3_ENDPOINT,
            region=Settings.S3_REGION,
            bucket_name=Settings.S3_BUCKET_NAME,
            domain=Settings.S3_DOMAIN,
        )


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

    cors_domains: str = ""
    trash_timeout: int = 30  # days
    singed_file_timeout: int = 60 * 60  # seconds
    jwt_secret: dict = json.loads(Settings.JWT_SECRET)

    def __hash__(self):
        return hash(self.model_dump_json())

    @property
    def s3_session_kwargs(self):
        return {
            "aws_access_key_id": (
                self.s3.access_key if self.s3 else Settings.S3_ACCESS_KEY
            ),
            "aws_secret_access_key": (
                self.s3.secret_key if self.s3 else Settings.S3_SECRET_KEY
            ),
        }

    @property
    def s3_client_kwargs(self):
        return {
            "service_name": "s3",
            "endpoint_url": self.s3.endpoint if self.s3 else Settings.S3_ENDPOINT,
            "region_name": self.s3.region if self.s3 else Settings.S3_REGION,
        }

    @property
    def s3_bucket(self):
        return self.s3.bucket_name if self.s3 else Settings.S3_BUCKET_NAME

    @property
    def s3_url(self):
        url = self.s3.domain if self.s3 else Settings.S3_DOMAIN
        return (url if url.startswith("http") else f"https://{url}").strip("/")


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

    @property
    def root_url(self):
        if self.domain.startswith("http"):
            return self.domain
        return f"https://{self.domain}"

    @classmethod
    async def get_by_origin(cls, origin: str):
        return await cls.find_one(cls.domain == origin)

    @model_validator(mode="before")
    def validate_domain(data: dict):
        if not data.get("domain"):
            business_name_domain = f"{data.get('name')}.{Settings.root_url}"
            data["domain"] = business_name_domain

        return data
