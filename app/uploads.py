from typing import Annotated

from fastapi import File, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from PIL import Image

from .config import Settings


async def single_image(request: Request, image: Annotated[UploadFile, File()]) -> UploadFile:
    form = await request.form()
    if len(form.getlist("image")) != 1:
        raise RequestValidationError([{
            "type": "value_error",
            "loc": ("body", "image"),
            "msg": "Exactly one image is required",
            "input": None,
        }])
    return image


def decode_image(upload: UploadFile, settings: Settings) -> Image.Image:
    if settings.max_image_bytes is not None and upload.size is not None:
        if upload.size > settings.max_image_bytes:
            raise HTTPException(413, "Image file too large")
    try:
        with Image.open(upload.file) as source:
            allowed = settings.allowed_image_formats
            if allowed is not None and source.format not in allowed:
                raise HTTPException(415, "Unsupported image format")
            return source.convert("RGB")
    except Image.DecompressionBombError as exc:
        raise HTTPException(413, "Image dimensions too large") from exc
    except (OSError, ValueError, SyntaxError, EOFError) as exc:
        raise HTTPException(415, "Unsupported or invalid image") from exc

