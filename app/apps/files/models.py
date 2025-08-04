from datetime import datetime
from pathlib import Path
from typing import ClassVar, Optional

from fastapi_mongo_base.models import BaseEntity, UserOwnedEntity
from pydantic import Field
from pymongo import ASCENDING, IndexModel
from usso.exceptions import PermissionDenied

from .schemas import FileMetaDataOut, Permission, PermissionEnum, PermissionSchema


class ObjectMetaData(BaseEntity):
    key: str
    size: int
    object_hash: str
    content_type: str

    access_at: datetime = Field(default_factory=datetime.now)
    url: str | None = None

    class Settings:
        keep_nulls = False
        validate_on_save = True

        indexes: ClassVar[list[IndexModel]] = [
            *BaseEntity.Settings.indexes,
            IndexModel([("key", ASCENDING)], unique=True),
        ]

    async def delete(self) -> None:
        from .file_manager import file_manager

        other_files = await FileMetaData.find({"key": self.key}).count()
        if other_files != 0:
            return

        await file_manager.delete_file(self)
        await super().delete()

    @classmethod
    async def delete_key(cls, key: str) -> None:
        from .file_manager import file_manager

        await file_manager.delete_file(key)
        item = await cls.find_one({"key": key})
        await item.delete()

    @classmethod
    async def get_key(cls, key: str) -> Optional["ObjectMetaData"]:
        return await cls.find_one({"key": key})


class FileMetaData(FileMetaDataOut, UserOwnedEntity):
    @classmethod
    def _get_permission_query(
        cls, *, user_id: str, root_permission: bool = False
    ) -> dict:
        if root_permission:
            return {}

        return {
            "$or": [
                {"user_id": user_id},
                {
                    "permissions": {
                        "$elemMatch": {
                            "user_id": user_id,
                            "permission": {"$gt": PermissionEnum.READ},
                        }
                    }
                },
                # {"public_permission": {"$gt": PermissionEnum.READ}},
            ]
        }

    @classmethod
    def get_queryset(
        cls,
        *,
        user_id: str | None = None,
        tenant_id: str | None = None,
        is_deleted: bool = False,
        uid: str | None = None,
        **kwargs: object,
    ) -> dict:
        """Build a MongoDB query filter based on provided parameters."""
        base_query = {}
        base_query.update({"is_deleted": is_deleted})
        if hasattr(cls, "tenant_id") and tenant_id:
            base_query.update({"tenant_id": tenant_id})
        if hasattr(cls, "user_id") and user_id:
            base_query.update(
                cls._get_permission_query(
                    user_id=user_id,
                    root_permission=kwargs.get("root_permission", False),
                )
            )
        if uid:
            base_query.update({"uid": uid})
        # Extract extra filters from kwargs
        extra_filters = cls._build_extra_filters(**kwargs)
        base_query.update(extra_filters)
        return base_query

    @classmethod
    async def list_items(
        cls,
        *,
        user_id: str,
        offset: int = 0,
        limit: int = 10,
        sort_field: str = "updated_at",  # default sort field for latest edited items
        sort_direction: int = -1,  # descending order for latest items first
        root_permission: bool = False,
        uid: str | None = None,
        parent_id: str | None = None,
        filehash: str | None = None,
        filename: str | None = None,
        is_deleted: bool = False,
        is_directory: bool | None = None,
        content_type: str | None = None,
        **kwargs: object,
    ) -> tuple[list["FileMetaData"], int]:
        kwargs.update({
            "user_id": user_id,
            "offset": offset,
            "limit": limit,
            "sort_field": sort_field,
            "sort_direction": sort_direction,
            "root_permission": root_permission,
            "is_deleted": is_deleted,
            "parent_id": parent_id,
            "filehash": filehash,
            "filename": filename,
            "uid": uid,
            "is_directory": is_directory,
            "content_type": content_type,
        })
        return await super().list_items(**kwargs)

    @classmethod
    async def remove_no_key_files(cls) -> None:
        """
        This function is used to remove files that have no ObjectMetaData
        with the same key. It is used to clean up the database after a migration.
        """

        pipeline = [
            {"$match": {"key": {"$exists": True}}},
            {"$group": {"object_key": "$key"}},
            {
                "$lookup": {
                    "from": "ObjectMetaData",
                    "localField": "object_key",
                    "foreignField": "key",
                    "as": "ObjectMetaData",
                }
            },
            {"$match": {"ObjectMetaData": {"$size": 0}}},
        ]
        files = await cls.aggregate(pipeline).to_list()
        for file in files:
            # if i % 10 == 0:
            #     pass
            file = await cls.find_one({"key": file["object_key"]})
            if file:
                await file.delete(file.user_id)
                await file.delete(file.user_id)

    @classmethod
    async def get_item(
        cls,
        uid: str,
        *,
        user_id: str | None = None,
        root_permission: bool = False,
        **kwargs: object,
    ) -> "FileMetaData":
        return await super().get_item(
            uid,
            user_id=user_id,
            ignore_user_id=True,
            root_permission=root_permission,
            **kwargs,
        )

    @classmethod
    async def create_directory(
        cls,
        *,
        user_id: str,
        dirname: str,
        parent_id: str | None = None,
        **kwargs: object,
    ) -> "FileMetaData":
        res = cls(
            user_id=user_id,
            filename=dirname,
            is_directory=True,
            parent_id=parent_id,
            **kwargs,
        )
        await res.save()
        return res

    @classmethod
    async def get_path(
        cls,
        *,
        filepath: str,
        user_id: str,
        parent_id: str | None = None,
        create: bool = True,
    ) -> "FileMetaData":
        file_path: Path = Path(filepath.lstrip("/"))
        parts = file_path.parts

        for part in parts if filepath.endswith("/") else parts[:-1]:
            files = await cls.list_items(
                user_id=user_id,
                filename=part,
                is_directory=True,
                parent_id=parent_id,
            )
            if not files:
                if create:
                    files = [
                        await cls.create_directory(
                            user_id=user_id,
                            dirname=part,
                            parent_id=parent_id,
                        )
                    ]
                else:
                    raise FileNotFoundError(f"File not found: {part}")
            parent_id = files[0].uid

        return parent_id, (None if filepath.endswith("/") else parts[-1])

    def user_permission(self, user_id: str | None) -> PermissionSchema:
        if user_id is None:
            return self.public_permission

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

    async def set_permission(self, user_id: str, permission: Permission) -> None:
        if user_id != permission.user_id:
            raise PermissionDenied(detail="Permission denied")

        if permission.user_id == self.user_id:
            raise PermissionDenied(detail="Cannot change owner permission")

        for perm in self.permissions:
            if perm.user_id == permission.user_id:
                perm.permission = permission.permission
                perm.updated_at = datetime.now()
                return

        self.permissions.append(permission)

    @classmethod
    async def exists_key(cls, key: str) -> bool:
        return await cls.find_one({"key": key}) is not None

    async def soft_delete(self, user_id: str) -> None:
        """Mark a file as deleted without removing it from the system.
        This is the first step in the two-step deletion process."""
        if not self.user_permission(user_id).delete:
            raise PermissionDenied(detail="Permission denied")

        if self.is_directory:
            files: list[FileMetaData] = await self.list_items(
                user_id=user_id,
                parent_id=self.uid,
                is_deleted=self.is_deleted,
            )
            for file in files:
                if file.uid != self.uid:
                    await file.soft_delete(user_id)

        if not self.is_deleted:
            self.is_deleted = True
            self.deleted_at = datetime.now()
            await self.save()

    async def hard_delete(self, user_id: str) -> None:
        """Permanently remove the file and its associated data.
        This is the second step in the two-step deletion process."""
        if not self.user_permission(user_id).delete:
            raise PermissionDenied(detail="Permission denied")

        if not self.is_deleted:
            raise ValueError("File must be soft deleted first")

        if self.is_directory:
            files: list[FileMetaData] = await self.list_items(
                user_id=user_id,
                parent_id=self.uid,
                is_deleted=True,
            )
            for file in files:
                if file.uid != self.uid:
                    await file.hard_delete(user_id)

        if not await self.exists_key(self.key):
            object_meta = await ObjectMetaData.get_key(self.key)
            if object_meta:
                await object_meta.delete()
        await super().delete()

    async def delete(self, user_id: str) -> None:
        """Legacy delete method that performs both soft and hard delete.
        Maintained for backward compatibility."""
        if not self.is_deleted:
            await self.soft_delete(user_id)
        else:
            await self.hard_delete(user_id)

    async def restore(self, user_id: str) -> None:
        if not self.user_permission(user_id).delete:
            raise PermissionDenied(detail="Permission denied")

        if self.is_directory:
            files: list[FileMetaData] = await self.list_items(
                user_id=user_id,
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
    async def get_volume(cls, user_id: str) -> int:
        """Calculate the total file size for a user.

        :param user_id: str of the user
        :return: Total size of the files for the user
        """
        pipeline = [
            {
                "$match": {
                    "user_id": user_id,
                    "is_deleted": False,
                }
            },
            {"$group": {"_id": None, "total_size": {"$sum": "$size"}}},
        ]

        result = await cls.aggregate(pipeline).to_list(length=1)

        if result:
            return result[0].get("total_size", 0)
        return 0
