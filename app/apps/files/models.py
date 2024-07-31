import uuid
from datetime import datetime
from pathlib import Path

from apps.base.models import BusinessEntity, BusinessOwnedEntity
from bson import UUID_SUBTYPE, Binary
from pydantic import Field
from pymongo import ASCENDING, IndexModel
from server.config import Settings

from .schemas import Permission, PermissionEnum, PermissionSchema


class ObjectMetaData(BusinessEntity):
    s3_key: str
    size: int
    object_hash: str
    content_type: str

    access_at: datetime = Field(default_factory=datetime.now)

    url: str | None = None

    class Settings:
        keep_nulls = False
        validate_on_save = True

        indexes = [
            IndexModel([("s3_key", ASCENDING)], unique=True),
        ]


class FileMetaData(BusinessOwnedEntity):
    s3_key: str | None = None

    parent_id: uuid.UUID | None = None
    is_directory: bool = False

    root_url: str | None = None

    filehash: str | None = None
    filename: str

    content_type: str = "inode/directory"
    size: int = 4096
    deleted_at: datetime | None = None

    permissions: list[Permission] = []
    public_permission: PermissionSchema = PermissionSchema()

    @property
    def url(self) -> str:
        base_url = (
            self.root_url
            if self.root_url.startswith("http")
            else f"https://{self.root_url}"
        ).strip("/")

        return f"{base_url}/v1/f/{self.uid}/{self.filename}"

    @classmethod
    async def list_files(
        cls,
        user_id: str,
        business_name: str,
        offset: int = 0,
        limit: int = 10,
        *,
        parent_id: uuid.UUID | None = None,
        filehash: str | None = None,
        filename: str | None = None,
        file_id: uuid.UUID | None = None,
        is_deleted: bool = False,
        is_directory: bool | None = None,
        root_permission: bool = False,
    ) -> list["FileMetaData"]:
        offset = max(offset, 0)
        limit = min(limit, Settings.page_max_limit)

        if file_id:
            file_id = Binary.from_uuid(file_id, UUID_SUBTYPE)
            query = {"uid": file_id, "business_name": business_name}
            pipeline = [{"$match": query}, {"$skip": offset}, {"$limit": limit}]

            items = await cls.aggregate(pipeline).to_list()
            if not items:
                return []
            if len(items) > 1:
                raise ValueError("Multiple files found")
            item = cls(**items[0])
            if root_permission:
                return [item]
            if item.user_permission(user_id).read:
                return [item]
            return []

        if not user_id:
            return []

        b_user_id = Binary.from_uuid(user_id, UUID_SUBTYPE)
        permission_query = [
            {"user_id": b_user_id},
            {
                "permissions": {
                    "$elemMatch": {
                        "user_id": b_user_id,
                        "permission": {"$gt": PermissionEnum.READ},
                    }
                }
            },
        ]

        query = {
            "is_deleted": is_deleted,
            "business_name": business_name,
            "$or": permission_query,
            "parent_id": (
                Binary.from_uuid(parent_id, UUID_SUBTYPE) if parent_id else None
            ),
        }

        if filehash:
            query["filehash"] = filehash
            query.pop("parent_id", None)
        if filename:
            query["filename"] = filename
            query.pop("parent_id", None)
        if is_directory is not None:
            query["is_directory"] = is_directory

        pipeline = [{"$match": query}, {"$skip": offset}, {"$limit": limit}]

        # Execute query and return list of items
        items = await cls.aggregate(pipeline).to_list()
        return [cls(**item) for item in items]

    @classmethod
    async def get_file(
        cls,
        user_id: str,
        business_name: str,
        file_id: uuid.UUID,
        root_permission: bool = False,
    ) -> "FileMetaData":
        files = await cls.list_files(
            user_id=user_id,
            business_name=business_name,
            file_id=file_id,
            root_permission=root_permission,
        )
        if len(files) > 1:
            raise ValueError("Multiple files found")
        if files:
            return files[0]

    @classmethod
    async def create_directory(
        cls,
        user_id: uuid.UUID,
        business_name: str,
        dirname: str,
        parent_id: uuid.UUID | None = None,
    ) -> "FileMetaData":
        res = cls(
            user_id=user_id,
            business_name=business_name,
            filename=dirname,
            is_directory=True,
            parent_id=parent_id,
        )
        await res.save()
        return res

    @classmethod
    async def get_path(
        cls,
        filepath: str,
        business_name: str,
        user_id: uuid.UUID,
        parent_id=None,
        create=True,
    ) -> "FileMetaData":
        if filepath.endswith("/"):
            raise ValueError("Invalid filepath")
        filepath: Path = Path(filepath.lstrip("/"))
        parts = filepath.parts

        for part in parts[:-1]:
            files = await cls.list_files(
                user_id=user_id,
                business_name=business_name,
                filename=part,
                is_directory=True,
                parent_id=parent_id,
            )
            if not files:
                if create:
                    files = [
                        await cls.create_directory(
                            user_id=user_id,
                            business_name=business_name,
                            dirname=part,
                            parent_id=parent_id,
                        )
                    ]
                else:
                    raise FileNotFoundError(f"File not found: {part}")
            parent_id = files[0].uid

        return parent_id, parts[-1]

    async def app_permission(self, app_id: str) -> PermissionSchema:
        for perm in self.permissions:
            if perm.user_id == app_id:
                return perm

        return self.public_permission

    def user_permission(self, user_id: uuid.UUID | None) -> PermissionSchema:
        if user_id is None:
            return self.public_permission

        if isinstance(user_id, str):
            user_id = uuid.UUID(user_id)

        if self.user_id == user_id:
            return Permission(
                created_at=self.created_at,
                updated_at=self.updated_at,
                user_id=user_id,
                permission=PermissionEnum.OWNER,
                uid=self.uid,
                read=True,
                write=True,
                delete=True,
            )

        for perm in self.permissions:
            if perm.user_id == user_id:
                return perm

        return self.public_permission
