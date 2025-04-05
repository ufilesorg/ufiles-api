import uuid
from datetime import datetime
from enum import Enum

from fastapi_mongo_base.schemas import BusinessOwnedEntitySchema, CoreEntitySchema
from pydantic import BaseModel, Field, field_validator


class PermissionEnum(int, Enum):
    NONE = 0
    READ = 10
    WRITE = 20
    MANAGE = 30
    DELETE = 40
    OWNER = 100


class PermissionSchema(CoreEntitySchema):
    permission: PermissionEnum = Field(default=PermissionEnum.NONE)

    @field_validator("permission", mode="before")
    def validate_permission(cls, v):
        if isinstance(v, str):
            try:
                return PermissionEnum[v.upper()]
            except KeyError:
                raise ValueError(f"Invalid permission string: {v}")
        return v

    @property
    def read(self):
        return self.permission >= PermissionEnum.READ

    @property
    def write(self):
        return self.permission >= PermissionEnum.WRITE

    @property
    def manage(self):
        return self.permission >= PermissionEnum.MANAGE

    @property
    def delete(self):
        return self.permission >= PermissionEnum.DELETE

    @property
    def owner(self):
        return self.permission >= PermissionEnum.OWNER


class Permission(PermissionSchema):
    user_id: uuid.UUID


class FileMetaDataCreate(BaseModel):
    parent_id: uuid.UUID | None = None
    is_directory: bool = False
    filename: str

    permissions: list[Permission] = []
    public_permission: PermissionSchema = PermissionSchema()


class FileMetaDataOut(FileMetaDataCreate, BusinessOwnedEntitySchema):
    s3_key: str | None = None

    url: str | None = None

    filehash: str | None = None

    access_at: datetime

    content_type: str
    size: int = 4096
    deleted_at: datetime | None = None

    icon: str | None = None
    preview: str | None = None


class FileMetaDataUpdate(BaseModel):
    is_deleted: bool | None = None
    parent_id: uuid.UUID | None = None
    filename: str | None = None

    permissions: list[Permission] = []
    public_permission: PermissionSchema | None = None

    @property
    def need_manage_permissions(self) -> bool:
        return self.permissions or self.public_permission


class MultiPartOut(BaseModel):
    upload_id: str


class PartUploadOut(BaseModel):
    part_number: int
    etag: str


class VolumeOut(BaseModel):
    volume: int = Field(
        description="Total size in bytes of all files owned by the requesting user"
    )
    max_volume: int = Field(
        default=0,
        description="Maximum size in bytes of all files owned by the requesting user",
    )
