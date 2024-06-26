import logging
from sqlalchemy import select
from apps.base.routes import AbstractBaseRouter
from apps.files.models import Business, BusinessPydantic
from apps.files.models import File as file
from apps.files.models import FilePydantic, Object, ObjectPydantic

# from apps.files.services import delete_file_from_s3, save_file_to_s3
from core.exceptions import BaseHTTPException
from fastapi import Depends, File, Request, UploadFile
from server.db import AsyncSession, get_session
from usso import UserData
from usso.exceptions import USSOException
from usso.fastapi import jwt_access_security


class FilesRouter(AbstractBaseRouter[FilePydantic]):
    def __init__(self):
        super().__init__(
            model=FilePydantic,
            user_dependency=jwt_access_security,
            resource_name="/files",
            tags=["files"],
        )

    async def list_items(
        self,
        request: Request,
        user: UserData = Depends(jwt_access_security),
        db: AsyncSession = Depends(get_session),
    ):
        domain = str(request.base_url)
        result = await db.execute(select(Business).filter(Business.domain == domain))
        business = result.scalars().first()
        if not business:
            raise BaseHTTPException(status_code=404,message="Business not found",error="")
    
        files = await db.execute(select(file).filter(file.business_id==business.id,file.parent==user.id))
        if not files:
            raise BaseHTTPException(status_code=404,message="user files not found",error="")
    
        return files


router = FilesRouter().router


# @router.post("/upload", response_model=FileMetadata)
# async def upload_file(file: UploadFile = File(...), user=Depends(jwt_access_security)):
#     if user is None:
#         raise USSOException(status_code=401, error="unauthorized")
#     file_metadata = await save_file_to_s3(file, user)
#     await file_metadata.save()

#     return file_metadata


# @router.get("/{filehash}", response_model=FileMetadata)
# async def get_file(filehash: str, user=Depends(jwt_access_security)):
#     file = FileMetadata.list().get(filehash)
#     if file is None:
#         raise BaseHTTPException(
#             status_code=404, error="file_not_found", message="File not found"
#         )
#     response = FileMetadata(**file)
#     if response.user_id != user.uid:
#         raise BaseHTTPException(status_code=403, error="forbidden", message="Forbidden")

#     return response


# @router.delete("/{filehash}")
# async def delete_file_endpoint(filehash: str, user=Depends(jwt_access_security)):
#     file: FileMetadata = await get_file(filehash, user)
#     if file.user_id != user.uid:
#         raise BaseHTTPException(status_code=403, error="forbidden", message="Forbidden")

#     await delete_file_from_s3(file.s3_key)
#     await file.delete()
#     return {"message": "File deleted successfully"}
