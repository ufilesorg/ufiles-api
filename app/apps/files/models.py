import uuid
from datetime import datetime
from pathlib import Path

from bson import UUID_SUBTYPE, Binary
from fastapi_mongo_base.models import BusinessEntity, BusinessOwnedEntity
from pydantic import Field
from pymongo import ASCENDING, IndexModel
from server.config import Settings

from .schemas import Permission, PermissionEnum, PermissionSchema
from .statics import get_icon_from_mime_type


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

        indexes = BusinessEntity.Settings.indexes + [
            IndexModel([("s3_key", ASCENDING)], unique=True),
        ]

    async def delete(self):
        from apps.business.schemas import Config

        from .services import delete_file_from_s3

        other_files = await FileMetaData.find({"s3_key": self.s3_key}).count()
        if other_files != 0:
            return

        # business = await self.get_business()
        config = Config()
        await delete_file_from_s3(self.s3_key, config=config)
        await super().delete()

    @classmethod
    async def delete_s3_key(cls, s3_key: str):
        from apps.business.schemas import Config

        from .services import delete_file_from_s3

        config = Config()
        await delete_file_from_s3(s3_key, config=config)
        item = await cls.find_one({"s3_key": s3_key})
        await item.delete()


class FileMetaData(BusinessOwnedEntity):
    s3_key: str | None = None

    parent_id: uuid.UUID | None = None
    is_directory: bool = False

    root_url: str | None = None

    filehash: str | None = None
    filename: str

    access_at: datetime = Field(default_factory=datetime.now)
    content_type: str = "inode/directory"
    size: int = 4096
    deleted_at: datetime | None = None
    # thumbnail: str | None = None

    permissions: list[Permission] = []
    public_permission: PermissionSchema = PermissionSchema()

    history: list[dict] = []

    class Settings:
        indexes = BusinessOwnedEntity.Settings.indexes

    @property
    def url(self) -> str:
        if not self.root_url:
            return None
        base_url = (
            self.root_url
            if self.root_url.startswith("http")
            else f"https://{self.root_url}"
        ).strip("/")

        return f"{base_url}/v1/f/{self.uid}/{self.filename}"

    @property
    def thumbnail(self) -> str | None:
        if self.content_type.startswith("image/"):
            return self.url

        return get_icon_from_mime_type(self.content_type)

    @property
    def real_size(self) -> int:
        return self.size + sum(item.get("size", 0) for item in self.history)

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
        content_type: str | None = None,
        sort_field: str = "updated_at",  # default sort field for latest edited items
        sort_direction: int = -1,  # descending order for latest items first
    ) -> tuple[list["FileMetaData"], int]:
        offset = max(offset, 0)
        limit = min(limit, Settings.page_max_limit)

        if file_id:
            file_id = Binary.from_uuid(file_id, UUID_SUBTYPE)
            query = {"uid": file_id, "business_name": business_name}
            pipeline = [{"$match": query}, {"$skip": offset}, {"$limit": limit}]

            items = await cls.aggregate(pipeline).to_list()
            if not items:
                return [], 0
            if len(items) > 1:
                raise ValueError("Multiple files found")
            item = cls(**items[0])
            if root_permission:
                return [item], 1
            if item.user_permission(user_id).read:
                return [item], 1
            return [], 0

        if not user_id:
            return [], 0

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
            if parent_id is None:
                query.pop("parent_id", None)
        if is_directory is not None:
            query["is_directory"] = is_directory
        if is_deleted and parent_id is None:
            query.pop("parent_id", None)
        if content_type:
            query["content_type"] = content_type

        pipeline = [
            {"$match": query},
            {
                "$facet": {
                    "items": [
                        {"$sort": {sort_field: sort_direction}},
                        {"$skip": offset},
                        {"$limit": limit},
                    ],
                    "total_count": [{"$count": "count"}],
                }
            },
            # {"$skip": offset},
            # {"$limit": limit},
            # {"$sort": {sort_field: sort_direction}},
        ]

        result = await cls.aggregate(pipeline).to_list()
        items = result[0]["items"] if result else []
        total_count_document = (
            result[0]["total_count"] if result and result[0]["total_count"] else [{}]
        )
        total_items = total_count_document[0].get("count", 0)

        return [cls(**item) for item in items], total_items

        # Execute query and return list of items
        items = await cls.aggregate(pipeline).to_list()
        total_items = await cls.find(query).count()
        return [cls(**item) for item in items], total_items

    @classmethod
    async def get_file(
        cls,
        user_id: str,
        business_name: str,
        file_id: uuid.UUID,
        root_permission: bool = False,
    ) -> "FileMetaData":
        files, _ = await cls.list_files(
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
            files, _ = await cls.list_files(
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
            )

        for perm in self.permissions:
            if perm.user_id == user_id:
                return perm

        return self.public_permission

    async def set_permission(self, permission: Permission):
        if permission.user_id == self.user_id:
            raise PermissionError("Cannot change owner permission")

        for perm in self.permissions:
            if perm.user_id == permission.user_id:
                perm.permission = permission.permission
                perm.updated_at = datetime.now()
                return

        self.permissions.append(permission)

    async def delete(self, user_id: uuid.UUID):
        if not self.user_permission(user_id).delete:
            raise PermissionError("Permission denied")

        if self.is_directory:
            files, _ = await self.list_files(
                user_id=user_id,
                business_name=self.business_name,
                parent_id=self.uid,
                is_deleted=self.is_deleted,
            )
            for file in files:
                await file.delete(user_id)

        if not self.is_deleted:
            self.is_deleted = True
            self.deleted_at = datetime.now()
            await self.save()
            return

        await super().delete()
        other_files = await self.find({"s3_key": self.s3_key}).count()
        if other_files == 0:
            object_meta = await ObjectMetaData.find_one({"s3_key": self.s3_key})
            if object_meta:
                await object_meta.delete()

    async def restore(self, user_id: uuid.UUID):
        if not self.user_permission(user_id).delete:
            raise PermissionError("Permission denied")

        if self.is_directory:
            files, _ = await self.list_files(
                user_id=user_id,
                business_name=self.business_name,
                parent_id=self.uid,
                is_deleted=True,
            )
            for file in files:
                await file.restore(user_id)

        if self.is_deleted:
            self.is_deleted = False
            self.deleted_at = None
            await self.save()

    @classmethod
    async def get_volume(cls, user_id: uuid.UUID, business_name: str) -> int:
        """
        Calculate the total file size for a user with the specified business name.

        :param user_id: UUID of the user
        :param business_name: Name of the business
        :return: Total size of the files for the user and business
        """
        b_user_id = Binary.from_uuid(user_id, UUID_SUBTYPE)
        pipeline = [
            {
                "$match": {
                    "user_id": b_user_id,
                    "business_name": business_name,
                    "is_deleted": False,
                }
            },
            {"$group": {"_id": None, "total_size": {"$sum": "$size"}}},
        ]

        result = await cls.aggregate(pipeline).to_list(length=1)

        if result:
            return result[0].get("total_size", 0)
        return 0
