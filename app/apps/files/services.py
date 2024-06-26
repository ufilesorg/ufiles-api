import asyncio
import hashlib
import os
import secrets
from io import BytesIO

import aioboto3
import filetype
from fastapi import UploadFile
from usso import UserData

from apps.files.models import FileMetadata
from core.exceptions import BaseHTTPException
from server.config import Settings



def check_file_type(file: BytesIO) -> bool:
    file_info = filetype.guess(file)
    file.seek(0)  # Reset the file pointer to the beginning.

    if not file_info or file_info.mime not in Settings().ACCEPTED_FILE_TYPES:
        raise BaseHTTPException(
            status_code=400, error="unsupported", message="Unsupported file type"
        )
    return file_info.mime


async def upload_to_s3(file_bytes, s3_key, **kwargs):
    session = aioboto3.Session(
        aws_access_key_id=Settings.S3_ACCESS_KEY,
        aws_secret_access_key=Settings.S3_SECRET_KEY,
    )

    async with session.client(
        "s3", endpoint_url=Settings.S3_ENDPOINT, region_name=Settings.S3_REGION
    ) as s3_client:
        await s3_client.upload_fileobj(
            file_bytes, Bucket=Settings.S3_BUCKET_NAME, Key=s3_key
        )
        file_bytes.close()


async def save_file_to_s3(file: UploadFile, user: "UserData") -> "FileMetadata":
    file_bytes = BytesIO(await file.read())
    mime = check_file_type(file_bytes)

    basename, ext = os.path.splitext(file.filename)
    filename = f"{basename}_{secrets.token_urlsafe(6)}{ext}"
    filehash = hashlib.md5(file_bytes.getvalue()).hexdigest()
    size = len(file_bytes.getvalue())

    business_id = "542a4547-e7ec-465e-8118-5543dbf67651"  # Adjust this according to your actual logic to set business_id.
    s3_key = f"{business_id}/{filename}" if business_id else filename
    url = f"https://{Settings.S3_DOMAIN}/{s3_key}"

    asyncio.create_task(upload_to_s3(file_bytes, s3_key))

    metadata = FileMetadata(
        user_id=user.uid,
        business_id=business_id,
        filehash=filehash,
        filename=file.filename,
        s3_key=s3_key,
        url=url,
        content_type=mime,
        size=size,
    )
    return metadata


async def delete_file_from_s3(s3_key: str) -> None:
    session = aioboto3.Session(
        aws_access_key_id=Settings.S3_ACCESS_KEY,
        aws_secret_access_key=Settings.S3_SECRET_KEY,
    )

    async with session.client(
        "s3", endpoint_url=Settings.S3_ENDPOINT, region_name=Settings.S3_REGION
    ) as s3_client:
        await s3_client.delete_object(Bucket=Settings.S3_BUCKET_NAME, Key=s3_key)
