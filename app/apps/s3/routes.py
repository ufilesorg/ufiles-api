import os

from apps.business.middlewares import get_business
from core.exceptions import BaseHTTPException
from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from .services import verify_signature

router = APIRouter(prefix="/s3", tags=["s3"], include_in_schema=False)

STORAGE_DIR = "./storage"

if not os.path.exists(STORAGE_DIR):
    os.makedirs(STORAGE_DIR)


@router.put("/{bucket_name}/{object_name}")
async def upload_file(
    bucket_name: str,
    object_name: str,
    file: UploadFile = File(...),
    business=Depends(get_business),
    _=Depends(verify_signature),
):
    bucket_path = os.path.join(STORAGE_DIR, bucket_name)
    if not os.path.exists(bucket_path):
        os.makedirs(bucket_path)

    file_location = os.path.join(bucket_path, object_name)
    with open(file_location, "wb") as f:
        f.write(await file.read())
    return JSONResponse(
        status_code=200,
        content={"message": f"file '{object_name}' uploaded to bucket '{bucket_name}'"},
    )


@router.get("/{bucket_name}/{object_name}")
async def download_file(
    bucket_name: str,
    object_name: str,
    business=Depends(get_business),
    _=Depends(verify_signature),
):
    file_location = os.path.join(STORAGE_DIR, bucket_name, object_name)
    if os.path.exists(file_location):
        return FileResponse(file_location)
    else:
        raise BaseHTTPException(
            status_code=404, error="file_not_found", message="File not found"
        )


@router.delete("/{bucket_name}/{object_name}")
async def delete_file(
    bucket_name: str,
    object_name: str,
    business=Depends(get_business),
    _=Depends(verify_signature),
):
    file_location = os.path.join(STORAGE_DIR, bucket_name, object_name)
    if os.path.exists(file_location):
        os.remove(file_location)
        return JSONResponse(
            status_code=200,
            content={
                "message": f"file '{object_name}' deleted from bucket '{bucket_name}'"
            },
        )
    else:
        raise BaseHTTPException(
            status_code=404, error="file_not_found", message="File not found"
        )
