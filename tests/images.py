"""Photos generated for the tests: nothing here is a real picture."""

import io

from PIL import Image


def jpeg_bytes(size: tuple[int, int] = (60, 80)) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", size, "steelblue").save(out, format="JPEG")
    return out.getvalue()


def png_bytes(size: tuple[int, int] = (60, 80), mode: str = "RGBA") -> bytes:
    out = io.BytesIO()
    Image.new(mode, size).save(out, format="PNG")
    return out.getvalue()
