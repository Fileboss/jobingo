"""Checking an uploaded photo. Re-encoding bounds its weight and dimensions, and drops
any EXIF block (GPS position, camera, date) and comment the original carries."""

import base64
import binascii
import io

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_UPLOAD_BYTES = 8 * 1024 * 1024
MAX_SOURCE_PIXELS = 40_000_000
MAX_SIDE = 800  # pixels, after re-encoding
JPEG_QUALITY = 88


class InvalidPhotoError(Exception):
    """The upload is not a usable JPEG or PNG. The message is shown to the user."""


def decode_upload(data_base64: str) -> bytes:
    """The uploaded bytes, re-encoded as a JPEG."""
    if len(data_base64) > (MAX_UPLOAD_BYTES + 2) // 3 * 4:
        raise InvalidPhotoError(
            f"Photo trop lourde ({MAX_UPLOAD_BYTES // (1024 * 1024)} Mo au maximum)."
        )
    try:
        data = base64.b64decode(data_base64, validate=True)
    except (binascii.Error, ValueError) as error:
        raise InvalidPhotoError("Fichier image illisible.") from error
    return _reencode(data)


def _reencode(data: bytes) -> bytes:
    if not data:
        raise InvalidPhotoError("Aucun fichier reçu.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise InvalidPhotoError(
            f"Photo trop lourde ({MAX_UPLOAD_BYTES // (1024 * 1024)} Mo au maximum)."
        )
    try:
        with Image.open(io.BytesIO(data)) as source:
            if source.format not in ("JPEG", "PNG"):
                raise InvalidPhotoError("Formats acceptés : JPEG et PNG.")
            if source.width * source.height > MAX_SOURCE_PIXELS:
                raise InvalidPhotoError("Photo trop grande (40 mégapixels au maximum).")
            image = ImageOps.exif_transpose(source)
            if image.mode in ("RGBA", "LA", "P"):
                image = image.convert("RGBA")
                # JPEG has no alpha: flatten on white rather than on black.
                flat = Image.new("RGB", image.size, "white")
                flat.paste(image, mask=image.getchannel("A"))
                image = flat
            image = image.convert("RGB")
            image.thumbnail((MAX_SIDE, MAX_SIDE))
            image.info.clear()  # the encoder would otherwise write the source's comment back
            out = io.BytesIO()
            image.save(out, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
        raise InvalidPhotoError("Fichier image illisible.") from error
    return out.getvalue()
