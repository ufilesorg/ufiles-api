import uuid
from datetime import datetime

from apps.base.models import BusinessEntity, BusinessOwnedEntity
from apps.base.schemas import OwnedEntitySchema
from pydantic import Field


class ObjectMetadata(BusinessEntity):
    s3_key: str
    size: int
    object_hash: str
    content_type: str

    access_at: datetime = Field(default_factory=datetime.now)

    url: str


class Permission(OwnedEntitySchema):
    read: bool = False
    write: bool = False
    delete: bool = False


class FileMetadata(BusinessOwnedEntity):
    object_id: uuid.UUID

    parent_id: uuid.UUID | None = None
    is_directory: bool = False

    filehash: str
    filename: str

    url: str

    content_type: str
    size: int
    delete_at: datetime | None = None

    permission: list[Permission] = []
    public_permission: Permission = Permission()

    def permissions(self, user_id: str) -> Permission:
        for perm in self.permission:
            if perm.user_id == user_id:
                return perm

        return self.public_permission
    
    @classmethod
    async def list_files_for_user(
        cls, 
        user_id: str,
        business_id: uuid.UUID,
        offset: int,
        limit: int,
        parent_id: uuid.UUID | None = None,
    ):
        # Query to find public read permissions
        public_read_query = cls.find(
            cls.is_deleted == False,
            cls.business_id == business_id,
            cls.parent_id == parent_id,
            cls.is_directory == False,
            cls.public_permission.read == True,
        )

        # Query to find files with user-specific read permissions
        user_read_query = cls.find(
            cls.is_deleted == False,
            cls.business_id == business_id,
            cls.parent_id == parent_id,
            cls.is_directory == False,
            cls.permission.filter(
                lambda perm: perm.user_id == user_id and perm.read == True
            ).exists(),
        )

        # Combine both queries
        combined_query = (
            public_read_query.union(user_read_query)
            .sort("-created_at")
            .skip(offset)
            .limit(limit)
        )

        # Execute query and return list of items
        items = await combined_query.to_list()
        return items
