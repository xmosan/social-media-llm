"""Decode untrusted uploads before storing publicly served image bytes."""
import io
from pathlib import Path
import warnings
from uuid import uuid4

from fastapi import HTTPException
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_IMAGE_PIXELS = 16_000_000


def save_image_upload(upload, directory, prefix="upload"):
    data = upload.file.read(MAX_IMAGE_BYTES + 1)
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(413, "Use an image smaller than 10 MB.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                if (image.format not in {"JPEG", "PNG", "WEBP"} or getattr(image, "n_frames", 1) != 1
                        or image.width * image.height > MAX_IMAGE_PIXELS):
                    raise ValueError()
                image.load()
                # Re-encode actual pixels; strips EXIF/location and appended data.
                clean = ImageOps.exif_transpose(image).convert("RGB")
                output = io.BytesIO()
                clean.save(output, format="JPEG", quality=95)
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError,
            Image.DecompressionBombWarning):
        raise HTTPException(422, "Use a valid, still PNG, JPG or WEBP image up to 16 megapixels.") from None
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{prefix}_{uuid4().hex}.jpg"
    path.write_bytes(output.getvalue())
    return path.name, str(path)
