import uuid
from datetime import datetime
from enum import Enum

from apps.base.schemas import BusinessOwnedEntitySchema, CoreEntitySchema
from pydantic import BaseModel, Field


class PermissionEnum(int, Enum):
    NONE = 0
    READ = 10
    WRITE = 20
    MANAGE = 30
    DELETE = 40
    OWNER = 100


class PermissionSchema(CoreEntitySchema):
    permission: PermissionEnum = Field(default=PermissionEnum.NONE)

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


class FileMetaDataOut(BusinessOwnedEntitySchema):
    s3_key: str | None = None

    parent_id: uuid.UUID | None = None
    is_directory: bool = False

    url: str | None = None

    filehash: str | None = None
    filename: str

    access_at: datetime

    content_type: str
    size: int = 4096
    deleted_at: datetime | None = None

    permissions: list[Permission] = []
    public_permission: PermissionSchema = PermissionSchema()


class FileMetaDataUpdate(BaseModel):
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
