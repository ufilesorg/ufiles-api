from datetime import datetime

from sqlalchemy import UUID, Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class BaseModel(Base):
    __abstract__ = True
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now)
    is_deleted = Column(Boolean, default=False)


class Business(BaseModel):
    __tablename__ = "business"
    id = Column(Integer, primary_key=True, index=True)
    domin = Column(String)
    s3_bucket_name = Column(String, nullable=True)
    s3_domain = Column(String, nullable=True)
    s3_endpoint = Column(String, nullable=True)
    s3_access_key = Column(String, nullable=True)
    s3_secret_key = Column(String, nullable=True)
    s3_region = Column(String, nullable=True)
    is_public = Column(Boolean, default=False)


class File(BaseModel):
    __tablename__ = "files"
    id = Column(Integer, primary_key=True, index=True)
    business_id = Column(Integer, ForeignKey("business.id"))
    parent = Column(UUID)
    is_directory = Column(Boolean, default=False)
    s3_key = Column(String, ForeignKey("objects.s3_key"))
    object = relationship("Object", back_populates="file")


class Object(BaseModel):
    __tablename__ = "objects"
    s3_key = Column(String, primary_key=True, index=True)
    url = Column(String, nullable=True)
    size = Column(Integer)
    object_hash = Column(String)
    content_type = Column(String)
    files = relationship("File", back_populates="objects")


from datetime import datetime
from pydantic import BaseModel, Field
from typing import Optional, List
from uuid import UUID


class BaseModelPydantic(BaseModel):
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    is_deleted: bool = False


class BusinessPydantic(BaseModelPydantic):
    id: int
    domin: str
    s3_bucket_name: Optional[str] = None
    s3_domain: Optional[str] = None
    s3_endpoint: Optional[str] = None
    s3_access_key: Optional[str] = None
    s3_secret_key: Optional[str] = None
    s3_region: Optional[str] = None
    is_public: bool = False


class FilePydantic(BaseModelPydantic):
    id: int
    business: BusinessPydantic
    parent: Optional[UUID] = None
    is_directory: bool = False
    s3_key: str
    object: Optional["ObjectPydantic"] = None


class ObjectPydantic(BaseModelPydantic):
    s3_key: str
    url: Optional[str] = None
    size: int
    object_hash: str
    content_type: str
    files: Optional[List[FilePydantic]] = None

