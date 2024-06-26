from fastapi import Depends, File, Request, UploadFile
from usso import UserData
from usso.exceptions import USSOException
from usso.fastapi import jwt_access_security

from apps.base.routes import AbstractBaseRouter
from apps.files.models import Business,BusinessPydantic
from apps.files.models import File as file,FilePydantic
from apps.files.models import Object,ObjectPydantic
# from apps.files.services import delete_file_from_s3, save_file_to_s3
from core.exceptions import BaseHTTPException
from server.db import Session, get_session


class FilesRouter(AbstractBaseRouter[FilePydantic]):
    def __init__(self):
        super().__init__(
            model=FilePydantic,
            user_dependency=jwt_access_security,
            resource_name="/files",
            tags=["files"],
        )

    async def list_items(
        self, request: Request, user: UserData = None#Depends(jwt_access_security)
    ):
        user: UserData = await self.get_user(request)
        db: Session = get_session()
        domin = request.base_url
        business =await db.query(Business).first(Business.domin == domin)
        print(domin, business)
        files =await db.query(file).filter(file.parent == user.id).all()
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
