import uuid
from datetime import datetime

from apps.base.models import BusinessEntity, BusinessOwnedEntity
from bson import UUID_SUBTYPE, Binary
from pydantic import Field
from pymongo import ASCENDING, IndexModel
from server.config import Settings

from .schemas import Permission, PermissionSchema


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

        return f"{base_url}/files/{self.uid}"

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
        file_id: uuid.UUID | None = None,
        is_deleted: bool = False,
    ) -> list["FileMetaData"]:
        offset = max(offset, 0)
        limit = min(limit, Settings.page_max_limit)

        queries = [{"public_permission.read": True}]
        if user_id:
            b_user_id = Binary.from_uuid(user_id, UUID_SUBTYPE)
            queries += [
                {"user_id": b_user_id},
                {
                    "$and": [
                        {"permissions.user_id": b_user_id},
                        {"permissions.read": True},
                    ]
                },
            ]

        query = {
            "is_deleted": is_deleted,
            "business_name": business_name,
            "$or": queries,
            "parent_id": (
                Binary.from_uuid(parent_id, UUID_SUBTYPE) if parent_id else None
            ),
        }

        if filehash:
            query["filehash"] = filehash
            query.pop("parent_id", None)
        if file_id:
            query["uid"] = Binary.from_uuid(file_id, UUID_SUBTYPE)
            query.pop("parent_id", None)

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
        *,
        parent_id: uuid.UUID | None = None,
        filehash: str | None = None,
    ) -> "FileMetaData":
        files = await cls.list_files(
            user_id=user_id,
            business_name=business_name,
            file_id=file_id,
            parent_id=parent_id,
            filehash=filehash,
        )
        if len(files) > 1:
            raise ValueError("Multiple files found")
        if files:
            return files[0]

    async def app_permission(self, app_id: str) -> PermissionSchema:
        for perm in self.permissions:
            if perm.user_id == app_id:
                return perm

        return Permission(
            uid=self.uid,
            created_at=self.created_at,
            updated_at=self.updated_at,
            user_id=app_id,
            read=False,
            write=False,
            delete=False,
        )

    def user_permission(self, user_id: uuid.UUID) -> PermissionSchema:
        if isinstance(user_id, str):
            user_id = uuid.UUID(user_id)

        if self.user_id == user_id:
            return Permission(
                uid=self.uid,
                created_at=self.created_at,
                updated_at=self.updated_at,
                user_id=user_id,
                read=True,
                write=True,
                delete=True,
            )

        for perm in self.permissions:
            if perm.user_id == user_id:
                return perm

        return self.public_permission
