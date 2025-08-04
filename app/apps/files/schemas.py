from datetime import datetime
from enum import IntEnum

from fastapi_mongo_base.schemas import BaseEntitySchema, UserOwnedEntitySchema
from pydantic import BaseModel, Field, field_validator, model_validator

from server.config import Settings

from . import statics


class PermissionEnum(IntEnum):
    NONE = 0
    READ = 10
    WRITE = 20
    MANAGE = 30
    DELETE = 40
    OWNER = 100


class PermissionSchema(BaseEntitySchema):
    permission: PermissionEnum = Field(default=PermissionEnum.NONE)

    @field_validator("permission", mode="before")
    def validate_permission(cls, v: str | PermissionEnum) -> PermissionEnum:  # noqa: N805
        if isinstance(v, str):
            return PermissionEnum[v.upper()]
        return v

    @property
    def read(self) -> bool:
        return self.permission >= PermissionEnum.READ

    @property
    def write(self) -> bool:
        return self.permission >= PermissionEnum.WRITE

    @property
    def manage(self) -> bool:
        return self.permission >= PermissionEnum.MANAGE

    @property
    def delete(self) -> bool:
        return self.permission >= PermissionEnum.DELETE

    @property
    def owner(self) -> bool:
        return self.permission >= PermissionEnum.OWNER


class Permission(PermissionSchema):
    user_id: str


class FileMetaDataCreate(BaseModel):
    parent_id: str | None = None
    is_directory: bool = False
    filename: str

    permissions: list[Permission] = []
    public_permission: PermissionSchema = PermissionSchema()


class FileMetaDataSchema(FileMetaDataCreate, UserOwnedEntitySchema):
    key: str | None = None

    url: str | None = None

    filehash: str | None = None

    access_at: datetime = Field(default_factory=datetime.now)

    content_type: str
    size: int = 4096
    deleted_at: datetime | None = None

    icon: str | None = None
    preview: str | None = None

    history: list[dict] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_icon(cls, data: "FileMetaDataSchema") -> "FileMetaDataSchema":  # noqa: N805
        if data.icon is None:
            data.icon = statics.get_icon_from_mime_type(data.content_type)

        if data.url is None:
            data.url = "/".join([
                f"https://{Settings.root_url}{Settings.base_path}f",
                data.uid,
                data.filename,
            ])

        return data

    @field_validator("preview")
    def validate_preview(cls, preview: str | None) -> str | None:  # noqa: N805
        if preview is None:
            if cls.content_type.startswith("image/"):
                return cls.url

            if cls.content_type.startswith("video/"):
                return cls.url

        return preview

    @property
    def real_size(self) -> int:
        return self.size + sum(item.get("size", 0) for item in self.history)


class FileMetaDataUpdate(BaseModel):
    is_deleted: bool | None = None
    parent_id: str | None = None
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
