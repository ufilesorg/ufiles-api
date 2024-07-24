import uuid
from datetime import datetime
from enum import Enum

from apps.base.schemas import BusinessOwnedEntitySchema, CoreEntitySchema
from pydantic import BaseModel


class PermissionEnum(int, Enum):
    NONE: 0
    READ: 10
    WRITE: 20
    MANAGE: 30
    DELETE: 40
    OWNER: 100


class PermissionSchema(CoreEntitySchema):
    permission: PermissionEnum = PermissionEnum.NONE

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

    content_type: str
    size: int = 4096
    deleted_at: datetime | None = None

    permissions: list[Permission] = []
    public_permission: PermissionSchema = PermissionSchema()


class FileUploadMetaData(BaseModel):
    parent_id: uuid.UUID | None = None
    filename: str


class MultiPartOut(BaseModel):
    upload_id: str


class PartUploadOut(BaseModel):
    part_number: int
    etag: str
