from apps.business.middlewares import get_business
from apps.business.models import Business
from apps.business.routes import AbstractBusinessBaseRouter
from apps.files.models import FileMetadata
from apps.files.services import delete_file_from_s3, save_file_to_s3
from core.exceptions import BaseHTTPException
from fastapi import Depends, File, Request, UploadFile
from server.config import Settings
from usso.exceptions import USSOException
from usso import UserData
from usso.fastapi import jwt_access_security


class FilesRouter(AbstractBusinessBaseRouter[FileMetadata]):
    def __init__(self):
        super().__init__(
            model=FileMetadata,
            user_dependency=jwt_access_security,
            resource_name="/f",
            tags=["files"],
        )

    async def list_items(
        self,
        request: Request,
        offset: int = 0,
        limit: int = 10,
        business: Business = Depends(get_business),
        user=Depends(jwt_access_security),
        parent_id=None,
    ):
        user: UserData = await self.get_user(request)
        limit = max(limit, Settings.page_max_limit)

        items = await FileMetadata.list_files_for_user(
            user.uid, business.uid, offset, limit, parent_id
        )
        return items


router = FilesRouter().router


@router.post("/upload", response_model=FileMetadata)
async def upload_file(file: UploadFile = File(...), user=Depends(jwt_access_security)):
    if user is None:
        raise USSOException(status_code=401, error="unauthorized")
    file_metadata = await save_file_to_s3(file, user)
    await file_metadata.save()

    return file_metadata


@router.get("/{filehash}", response_model=FileMetadata)
async def get_file(filehash: str, user=Depends(jwt_access_security)):
    file = FileMetadata.list().get(filehash)
    if file is None:
        raise BaseHTTPException(
            status_code=404, error="file_not_found", message="File not found"
        )
    response = FileMetadata(**file)
    if response.user_id != user.uid:
        raise BaseHTTPException(status_code=403, error="forbidden", message="Forbidden")

    return response


@router.delete("/{filehash}")
async def delete_file_endpoint(filehash: str, user=Depends(jwt_access_security)):
    file: FileMetadata = await get_file(filehash, user)
    if file.user_id != user.uid:
        raise BaseHTTPException(status_code=403, error="forbidden", message="Forbidden")

    await delete_file_from_s3(file.s3_key)
    await file.delete()
    return {"message": "File deleted successfully"}
