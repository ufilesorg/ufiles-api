import json
from enum import Enum

from fastapi_mongo_base.schemas import OwnedEntitySchema
from pydantic import BaseModel
from server.config import Settings


class AccessType(str, Enum):
    public = "public"
    private = "private"
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
    jwt_config: dict = json.loads(Settings.JWT_CONFIG)

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


class BusinessSchema(OwnedEntitySchema):
    name: str
    description: str | None = None
    domain: str
    config: Config
