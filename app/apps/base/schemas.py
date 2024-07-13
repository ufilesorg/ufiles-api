import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class BaseEntitySchema(BaseModel):
    uid: uuid.UUID = Field(default_factory=uuid.uuid4, index=True, unique=True)
    created_at: datetime = Field(default_factory=datetime.now, index=True)
    updated_at: datetime = Field(default_factory=datetime.now)
    is_deleted: bool = False
    metadata: dict[str, Any] | None = None

    @property
    def create_exclude_set(self) -> list[str]:
        return ["uid", "created_at", "updated_at", "is_deleted"]

    @property
    def create_field_set(self) -> list:
        return []

    @property
    def update_exclude_set(self) -> list:
        return ["uid", "created_at", "updated_at"]

    @property
    def update_field_set(self) -> list:
        return []

    def model_dump_create(self):
        assert not (self.create_exclude_set and self.create_field_set)
        if self.create_field_set:
            return self.model_dump(fields=self.create_field_set)

        return self.model_dump(exclude=self.create_exclude_set)

    def model_dump_update(self):
        assert not (self.update_exclude_set and self.update_field_set)
        if self.update_field_set:
            return self.model_dump(fields=self.update_field_set)

        return self.model_dump(exclude=self.update_exclude_set)

    def expired(self, days: int = 3):
        return (datetime.now() - self.updated_at).days > days


class OwnedEntitySchema(BaseEntitySchema):
    user_id: uuid.UUID

    @property
    def create_exclude_set(self) -> list[str]:
        return ["uid", "created_at", "updated_at", "is_deleted", "user_id"]

    @property
    def update_exclude_set(self) -> list[str]:
        return ["uid", "created_at", "updated_at", "user_id"]

    def model_dump_create(self, user_id: uuid.UUID):
        assert not (self.create_exclude_set and self.create_field_set)
        if self.create_field_set:
            return self.model_dump(fields=self.create_field_set) | {"user_id": user_id}

        return self.model_dump(exclude=self.create_exclude_set) | {"user_id": user_id}


class BusinessEntitySchema(BaseEntitySchema):
    business_id: uuid.UUID

    @property
    def create_exclude_set(self) -> list[str]:
        return ["uid", "created_at", "updated_at", "is_deleted", "business_id"]

    @property
    def update_exclude_set(self) -> list[str]:
        return ["uid", "created_at", "updated_at", "business_id"]

    def model_dump_create(self, business_id: uuid.UUID):
        assert not (self.create_exclude_set and self.create_field_set)
        if self.create_field_set:
            return self.model_dump(fields=self.create_field_set) | {
                "business_id": business_id
            }

        return self.model_dump(exclude=self.create_exclude_set) | {
            "business_id": business_id
        }


class BusinessOwnedEntitySchema(OwnedEntitySchema, BusinessEntitySchema):

    @property
    def create_exclude_set(self) -> list[str]:
        return [
            "uid",
            "created_at",
            "updated_at",
            "is_deleted",
            "business_id",
            "user_id",
        ]

    @property
    def update_exclude_set(self) -> list[str]:
        return ["uid", "created_at", "updated_at", "business_id", "user_id"]

    def model_dump_create(self, business_id: uuid.UUID, user_id: uuid.UUID):
        assert not (self.create_exclude_set and self.create_field_set)
        if self.create_field_set:
            return self.model_dump(fields=self.create_field_set) | {
                "business_id": business_id,
                "user_id": user_id,
            }

        return self.model_dump(exclude=self.create_exclude_set) | {
            "business_id": business_id,
            "user_id": user_id,
        }


class Language(str, Enum):
    English = "English"
    Persian = "Persian"
