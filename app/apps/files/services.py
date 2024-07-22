import asyncio
import hashlib
import os
import uuid
from functools import lru_cache
from io import BytesIO
from typing import AsyncGenerator

import aioboto3
import aiofiles
import magic
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from fastapi import UploadFile
from usso import UserData
from pathlib import Path

from apps.business.models import AccessType, Business, Config
from apps.files.models import FileMetaData, ObjectMetaData, PermissionSchema
from core.exceptions import BaseHTTPException
from server.config import Settings


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


async def calculate_file_hash(file: UploadFile) -> str:
    file_hash = hashlib.md5()
    file.file.seek(0)  # Ensure we start from the beginning of the file
    async with aiofiles.open(file.file, "rb") as f:
        while chunk := await f.read(8192):
            file_hash.update(chunk)
    file.file.seek(0)  # Reset file pointer to the beginning
    return file_hash.hexdigest()


async def check_file(file: BytesIO, config: Config, **kwargs):
    mime = check_file_type(file, config.accepted_file_types)

    size = len(file.getvalue())
    if size > config.size_limits:
        raise BaseHTTPException(
            status_code=400,
            error="file_too_large",
            message="File size exceeds the maximum allowed size",
        )

    # check for security (svg valid scripts)
    # convert if requested (ico, svg -> webp)

    return mime, size


async def process_file(
    file: UploadFile,
    user: "UserData",
    business: Business,
    parent_id: uuid.UUID | None = None,
    filename: str | None = None,
    blocking: bool = False,
    **kwargs,
) -> FileMetaData:
    file_bytes = BytesIO(await file.read())

    if filename:
        if '/' in filename:
            if filename[-1] == '/':
                raise BaseHTTPException(
                    status_code=400,
                    error="invalid_filename",
                    message="Filename cannot end with a slash",
                )
            parent_id = await FileMetaData.get_path(filename, business.name, user.uid)
        file_bytes.name = filename
    else:
        file_bytes.name = file.filename

    mime, size = await check_file(file_bytes, business.config)

    filehash = hashlib.md5(file_bytes.getvalue()).hexdigest()

    # basename, ext = os.path.splitext(file.filename)
    # filename = f"{basename}_{secrets.token_urlsafe(6)}{ext}"
    filename = file_bytes.name

    s3_key = f"{business.name}/{user.b64id}/{filename}" if business.name else filename

    upload_task = asyncio.create_task(
        manage_upload_to_s3(
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
        filename=filename,
        s3_key=s3_key,
        root_url=business.root_url,
        content_type=mime,
        size=size,
        parent_id=parent_id,
        public_permission=PermissionSchema(
            read=(business.config.access_type == AccessType.public)
        ),
    )
    return metadata


@lru_cache
def get_session(config: Config):
    return aioboto3.Session(**config.s3_session_kwargs)


async def upload_to_s3(
    file_bytes: BytesIO,
    s3_key: str,
    *,
    config: Config = None,
    **kwargs,
):
    config = config or Config()
    session = get_session(config)

    async with session.client(**config.s3_client_kwargs) as s3_client:
        await s3_client.upload_fileobj(file_bytes, Bucket=config.s3_bucket, Key=s3_key)


async def manage_upload_to_s3(
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

    if size > 100 * 1024 * 1024:
        await upload_to_s3_multipart(
            file_bytes, s3_key, chunk_size=100 * 1024 * 1024, config=config, **kwargs
        )
    else:
        await upload_to_s3(file_bytes, s3_key, config=config, **kwargs)

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


async def create_multipart_upload(client, bucket, key):
    response = await client.create_multipart_upload(Bucket=bucket, Key=key)
    return response["UploadId"]


async def upload_part(client, bucket, key, upload_id, part_number, data):
    response = await client.upload_part(
        Bucket=bucket, Key=key, PartNumber=part_number, UploadId=upload_id, Body=data
    )
    return {"PartNumber": part_number, "ETag": response["ETag"]}


async def complete_multipart_upload(client, bucket, key, upload_id, parts):
    await client.complete_multipart_upload(
        Bucket=bucket, Key=key, UploadId=upload_id, MultipartUpload={"Parts": parts}
    )


async def upload_to_s3_multipart(
    file_bytes: BytesIO,
    s3_key: str,
    chunk_size: int = 5 * 1024 * 1024,  # 5 MB
    *,
    config: Config = None,
    **kwargs,
):
    config = config or Config()

    session = get_session(config)
    async with session.client(**config.s3_client_kwargs) as s3_client:
        upload_id = await create_multipart_upload(s3_client, config.s3_bucket, s3_key)

        file_bytes.seek(0, 2)  # Move to the end of the BytesIO
        file_bytes.tell()
        file_bytes.seek(0)  # Reset to the beginning

        parts = []
        part_number = 1
        while True:
            chunk = file_bytes.read(chunk_size)
            if not chunk:
                break
            part = await upload_part(
                s3_client, config.s3_bucket, s3_key, upload_id, part_number, chunk
            )
            parts.append(part)
            part_number += 1

        await complete_multipart_upload(
            s3_client, config.s3_bucket, s3_key, upload_id, parts
        )


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


async def stream_from_s3(s3_key, *, config: Config = None, **kwargs):
    config = config or Config()
    session = get_session(config)

    async with session.client(**config.s3_client_kwargs) as s3_client:
        response = await s3_client.get_object(Bucket=config.s3_bucket, Key=s3_key)

        async for chunk in response["Body"].iter_chunks():
            yield chunk


async def stream_from_s3_and_encrypt(
    s3_key, encryption_key: bytes, *, config=None, **kwargs
) -> AsyncGenerator[bytes, None]:
    config = config or Config()
    session = get_session(config)
    iv = os.urandom(16)

    encryption_key = (
        encryption_key if isinstance(encryption_key, bytes) else encryption_key.encode()
    )
    # Create AES-CTR cipher
    cipher = Cipher(
        algorithms.AES(encryption_key), modes.CTR(iv), backend=default_backend()
    )
    encryptor = cipher.encryptor()

    async with session.client(**config.s3_client_kwargs) as s3_client:
        response = await s3_client.get_object(Bucket=config.s3_bucket, Key=s3_key)

        # First, yield the IV since it's needed for decryption
        yield iv

        async for chunk in response["Body"].iter_chunks():
            # Encrypt the chunk
            encrypted_chunk = encryptor.update(chunk)
            yield encrypted_chunk

        # Finalize encryption
        encrypted_chunk = encryptor.finalize()
        if encrypted_chunk:
            yield encrypted_chunk


async def decrypt_stream(
    encryption_key: bytes, encrypted_stream: AsyncGenerator[bytes, None]
) -> AsyncGenerator[bytes, None]:

    # Read the IV from the stream first
    iv = await anext(encrypted_stream)
    encryption_key = (
        encryption_key if isinstance(encryption_key, bytes) else encryption_key.encode()
    )

    # Create AES-CTR cipher with the IV
    cipher = Cipher(
        algorithms.AES(encryption_key), modes.CTR(iv), backend=default_backend()
    )
    decryptor = cipher.decryptor()

    async for encrypted_chunk in encrypted_stream:
        # Decrypt the chunk
        decrypted_chunk = decryptor.update(encrypted_chunk)
        yield decrypted_chunk

    # Finalize decryption
    decrypted_chunk = decryptor.finalize()
    if decrypted_chunk:
        yield decrypted_chunk
