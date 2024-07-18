import asyncio
import hashlib
import os
import uuid
from functools import lru_cache
from io import BytesIO

import aioboto3
import magic
from apps.business.models import Business, Config
from apps.files.models import FileMetaData, ObjectMetaData
from core.exceptions import BaseHTTPException
from fastapi import UploadFile
from server.config import Settings
from usso import UserData


def check_file_type(file: BytesIO, accepted_mimes=Settings.ACCEPTED_FILE_TYPES) -> bool:
    file.seek(0)  # Reset the file pointer to the beginning.

    # Initialize the magic MIME type detector
    mime_detector = magic.Magic(mime=True)

    # Detect MIME type from the buffer
    mime_type = mime_detector.from_buffer(file.read(2048))  # Read the first 2048 bytes

    file.seek(0)  # Reset the file pointer to the beginning.

    if not mime_type or mime_type not in accepted_mimes:
        raise BaseHTTPException(
            status_code=400, error="unsupported", message="Unsupported file type"
        )
    return mime_type


@lru_cache
def get_session(config: Config):
    return aioboto3.Session(**config.s3_session_kwargs)


async def upload_to_s3(
    file_bytes: BytesIO,
    s3_key: str,
    business_name: str,
    filehash: str,
    content_type: str,
    size: int,
    *,
    config: Config = None,
    **kwargs,
):
    objects = await ObjectMetaData.find(
        ObjectMetaData.business_name == business_name, ObjectMetaData.s3_key == s3_key
    ).to_list()
    if objects:
        return objects[0]

    config = config or Config()
    session = get_session(config)

    async with session.client(**config.s3_client_kwargs) as s3_client:
        await s3_client.upload_fileobj(file_bytes, Bucket=config.s3_bucket, Key=s3_key)

    obj = ObjectMetaData(
        business_name=business_name,
        s3_key=s3_key,
        size=size,
        object_hash=filehash,
        content_type=content_type,
        url=f"{config.s3_url}/{s3_key}",
    )
    await obj.save()
    file_bytes.close()


async def save_file_to_s3(
    file: UploadFile,
    user: "UserData",
    business: Business,
    parent_id: uuid.UUID | None = None,
    filename: str | None = None,
    blocking: bool = False,
    **kwargs,
) -> "FileMetaData":
    file_bytes = BytesIO(await file.read())
    if filename:
        file_bytes.name = filename
    mime = check_file_type(file_bytes)

    size = len(file_bytes.getvalue())
    filehash = hashlib.md5(file_bytes.getvalue()).hexdigest()

    basename, ext = os.path.splitext(file.filename)
    # filename = f"{basename}_{secrets.token_urlsafe(6)}{ext}"
    filename = filehash

    s3_key = f"{business.name}/{user.b64id}/{filename}" if business.name else filename

    upload_task = asyncio.create_task(
        upload_to_s3(
            file_bytes,
            s3_key,
            business_name=business.name,
            size=size,
            filehash=filehash,
            content_type=mime,
            config=business.config,
            **kwargs,
        )
    )
    if blocking:
        await upload_task

    metadata = FileMetaData(
        user_id=user.uid,
        business_name=business.name,
        filehash=filehash,
        filename=file.filename,
        s3_key=s3_key,
        root_url=business.root_url,
        content_type=mime,
        size=size,
        parent_id=parent_id,
    )
    return metadata


async def delete_file_from_s3(s3_key: str, *, config: Config = None, **kwargs):
    config = config or Config()
    session = get_session(config)

    async with session.client(**config.s3_client_kwargs) as s3_client:
        await s3_client.delete_object(Bucket=config.s3_bucket, Key=s3_key)


async def generate_presigned_url(s3_key: str, *, config: Config = None, **kwargs):
    config = config or Config()
    session = get_session(config)

    async with session.client(**config.s3_client_kwargs) as s3_client:
        response = await s3_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": config.s3_bucket, "Key": s3_key},
            ExpiresIn=config.singed_file_timeout,
        )
        return response


async def download_from_s3(s3_key, *, config: Config = None, **kwargs):
    config = config or Config()
    session = get_session(config)

    async with session.client(**config.s3_client_kwargs) as s3_client:
        response = await s3_client.get_object(Bucket=config.s3_bucket, Key=s3_key)
        file_bytes = BytesIO(await response["Body"].read())

    return file_bytes
