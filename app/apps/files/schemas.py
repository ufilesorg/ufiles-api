import uuid
from datetime import datetime

from apps.base.schemas import (
    BaseEntitySchema,
    BusinessOwnedEntitySchema,
    OwnedEntitySchema,
)
from pydantic import BaseModel


class PermissionSchema(BaseEntitySchema):
    read: bool = False
    write: bool = False
    delete: bool = False


class Permission(PermissionSchema, OwnedEntitySchema):
    pass


class FileMetaDataOut(BusinessOwnedEntitySchema):
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
