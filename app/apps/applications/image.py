import aiohttp

from apps.files.models import FileMetaData
from apps.files.services import download_from_s3
from core.exceptions import BaseHTTPException
from utils import imagetools


async def extract_logo_colors(file: FileMetaData) -> list[str]:
    try:
        if file.metadata.get("colors"):
            return file.metadata["colors"]

        if file.content_type.split("/")[0] != "image":
            raise BaseHTTPException(
                status_code=400,
                error="invalid_file_type",
                message="File is not an image",
            )

        image_bytes = await download_from_s3(file.s3_key)

        if file.content_type == "image/svg+xml":
            image_bytes = imagetools.svg_to_webp(image_bytes)

        image_bytes = imagetools.resize_image_if_bigger(image_bytes, new_width=512)

        colors = imagetools.color_palette(image_bytes)
        file.metadata["colors"] = colors
        await file.save()

        return colors

    except aiohttp.ClientError:
        raise BaseHTTPException(
            status_code=404,
            error="item_not_found",
            message=f"Logo not found",
        )