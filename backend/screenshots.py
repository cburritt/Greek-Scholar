# canvas screenshots: checking, saving and serving the images
# the app never reads what is in the picture, the chair just looks at it

import io
import os
import re
import secrets
import warnings
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from PIL import Image, UnidentifiedImageError
from sqlmodel import Session

from auth import get_current_user
from database import get_session
from models import Screenshot, Submission, User

# tests point GS_UPLOAD_DIR somewhere else
UPLOAD_DIR = Path(os.environ.get("GS_UPLOAD_DIR", Path(__file__).parent / "uploads"))

MAX_BYTES = 5 * 1024 * 1024
# big screenshots are shrunk to this many pixels on the longest side
MAX_SIDE = 2500
# pillow refuses anything far bigger than this, so a tiny file can't unpack into a giant image
Image.MAX_IMAGE_PIXELS = 40_000_000

# pillow format -> content type and file extension
ALLOWED = {
    "PNG": ("image/png", "png"),
    "JPEG": ("image/jpeg", "jpg"),
    "WEBP": ("image/webp", "webp"),
}

# only names we made ourselves, so a bad name can never point outside the folder
NAME_RE = re.compile(r"^[0-9a-f]{32}\.(png|jpg|webp)$")

router = APIRouter(tags=["screenshots"])


class ImageError(ValueError):
    pass


def clean_image(data: bytes) -> tuple[bytes, str, str]:
    # opens the image for real, then saves a fresh copy, which drops exif, location and anything hidden
    if len(data) > MAX_BYTES:
        raise ImageError("The screenshot is too large (5 MB max)")
    if not data:
        raise ImageError("The screenshot is empty")

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as img:
                fmt = img.format
                if fmt not in ALLOWED:
                    raise ImageError("The screenshot has to be a PNG, JPG or WebP image")
                img.load()
                if fmt == "JPEG":
                    picture = img.convert("RGB")
                else:
                    picture = img.convert("RGBA")
    except ImageError:
        raise
    except (UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning, OSError, SyntaxError, ValueError):
        raise ImageError("That file isn't a readable image") from None

    picture.thumbnail((MAX_SIDE, MAX_SIDE))
    out = io.BytesIO()
    if fmt == "JPEG":
        picture.save(out, format="JPEG", quality=85)
    else:
        picture.save(out, format=fmt)

    content_type, ext = ALLOWED[fmt]
    return out.getvalue(), content_type, ext


def save_file(data: bytes, ext: str) -> str:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    name = secrets.token_hex(16) + "." + ext
    (UPLOAD_DIR / name).write_bytes(data)
    return name


def file_path(name: str) -> Path:
    if not NAME_RE.match(name):
        raise ValueError("bad screenshot file name")
    return UPLOAD_DIR / name


def delete_file(name: str):
    try:
        file_path(name).unlink(missing_ok=True)
    except ValueError:
        pass


@router.get("/screenshots/{screenshot_id}")
def get_screenshot(screenshot_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    shot = session.get(Screenshot, screenshot_id)
    sub = None
    if shot is not None:
        sub = session.get(Submission, shot.submission_id)

    # only the member who sent it and the chair, everyone else gets the same not found
    if sub is None or (user.role != "chair" and sub.user_id != user.id):
        raise HTTPException(status_code=404, detail="Screenshot not found")

    path = file_path(shot.file_name)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Screenshot not found")

    return FileResponse(
        path,
        media_type=shot.content_type,
        headers={
            # the browser must treat it as an image and nothing else
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'",
            "Content-Disposition": "inline",
            "Cache-Control": "private, no-store",
        },
    )
