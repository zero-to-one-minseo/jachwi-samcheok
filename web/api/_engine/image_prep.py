"""올린 사진·PDF를 API에 보낼 바이트로 준비한다(기술_확인.md 6장 순서).

결과 바이트는 부르는 쪽이 메모리에만 둔다. 이 모듈은 아무것도 저장하지 않는다.
"""

import io
import math
from dataclasses import dataclass
from typing import Literal

from PIL import Image, ImageOps

from . import settings

PrepErrorKind = Literal["너무 큼", "열 수 없음", "지원 안 함"]

_ALLOWED_FORMATS = {"JPEG", "MPO", "PNG"}
_HEIF_BRANDS = (b"heic", b"heix", b"hevc", b"hevx", b"heim", b"heis", b"mif1", b"msf1", b"avif")

MSG_TOO_BIG_IMAGE = "사진이 너무 커요. 화면 캡처나 더 작은 사진으로 올려 주세요."
MSG_TOO_BIG_PDF = "PDF가 너무 커요. 계약서 쪽만 골라 올리거나 사진으로 올려 주세요."
MSG_TOO_BIG_FILE = "파일이 너무 커요. 더 작은 파일로 올려 주세요."
MSG_CANNOT_OPEN = "파일을 열 수 없어요. 다시 찍거나 다시 올려 주세요."
MSG_HEIC = "HEIC 사진은 받을 수 없어요. 스크린샷이나 JPG로 바꿔 올려 주세요."
MSG_UNSUPPORTED = "JPG, PNG, PDF 파일만 올릴 수 있어요."


@dataclass(frozen=True)
class PreparedFile:
    ok: bool
    kind: Literal["image", "pdf"] | None
    data: bytes | None
    media_type: str | None
    width: int | None
    height: int | None
    error_kind: PrepErrorKind | None
    message: str


def _fail(kind: PrepErrorKind, message: str) -> PreparedFile:
    return PreparedFile(False, None, None, None, None, None, kind, message)


def image_tokens(width: int, height: int) -> int:
    patch = settings.IMAGE_PATCH_PX
    return math.ceil(width / patch) * math.ceil(height / patch)


def _scaled(width: int, height: int, long_side: int) -> tuple[int, int]:
    if width >= height:
        return long_side, max(1, round(height * long_side / width))
    return max(1, round(width * long_side / height)), long_side


def target_size(
    width: int,
    height: int,
    max_long: int | None = None,
    max_tokens: int | None = None,
) -> tuple[int, int]:
    """긴 변 상한과 그림 토큰 상한을 둘 다 지키는 가장 큰 크기. 키우지는 않는다.

    서버가 한 번 더 줄이면 글자가 흐려지니 여기서 한 번만 줄인다. 4:3이면 약 2,212x1,659.
    """
    max_long = max_long or settings.IMAGE_MAX_LONG_SIDE
    max_tokens = max_tokens or settings.IMAGE_MAX_TOKENS
    lo, hi = 1, min(max(width, height), max_long)
    if image_tokens(*_scaled(width, height, hi)) <= max_tokens:
        return _scaled(width, height, hi)
    # 긴 변 길이가 늘면 토큰 수도 줄지 않으니 이분 탐색으로 가장 큰 길이를 찾는다.
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if image_tokens(*_scaled(width, height, mid)) <= max_tokens:
            lo = mid
        else:
            hi = mid - 1
    return _scaled(width, height, lo)


def _is_heif(data: bytes) -> bool:
    return len(data) >= 12 and data[4:8] == b"ftyp" and data[8:12] in _HEIF_BRANDS


def _extension(filename: str | None) -> str:
    if not filename or "." not in filename:
        return ""
    return filename.rsplit(".", 1)[1].lower()


def prepare_upload(data: bytes, filename: str | None = None) -> PreparedFile:
    """업로드 바이트를 종류에 따라 준비한다. 종류는 확장자보다 파일 앞부분으로 판단한다."""
    if len(data) > settings.UPLOAD_MAX_MB * 1024 * 1024:
        return _fail("너무 큼", MSG_TOO_BIG_FILE)
    if data.startswith(b"%PDF-"):
        return prepare_pdf(data)
    if _is_heif(data) or _extension(filename) in ("heic", "heif"):
        return _fail("지원 안 함", MSG_HEIC)
    ext = _extension(filename)
    if ext and ext not in settings.UPLOAD_TYPES:
        return _fail("지원 안 함", MSG_UNSUPPORTED)
    return prepare_image(data)


def prepare_pdf(data: bytes) -> PreparedFile:
    if len(data) > settings.PDF_MAX_MB * 1024 * 1024:
        return _fail("너무 큼", MSG_TOO_BIG_PDF)
    if not data.startswith(b"%PDF-"):
        return _fail("열 수 없음", MSG_CANNOT_OPEN)
    return PreparedFile(True, "pdf", data, "application/pdf", None, None, None, "")


def prepare_image(data: bytes) -> PreparedFile:
    try:
        image = Image.open(io.BytesIO(data))
    except Image.DecompressionBombError:
        return _fail("너무 큼", MSG_TOO_BIG_IMAGE)
    except Exception:
        if _is_heif(data):
            return _fail("지원 안 함", MSG_HEIC)
        return _fail("열 수 없음", MSG_CANNOT_OPEN)

    try:
        if image.format not in _ALLOWED_FORMATS:
            return _fail("지원 안 함", MSG_UNSUPPORTED)
        width, height = image.size
        # 화소 경고(DecompressionBombWarning)는 try로 잡히지 않아서 상한을 직접 비교한다.
        if width * height > settings.IMAGE_MAX_PIXELS:
            return _fail("너무 큼", MSG_TOO_BIG_IMAGE)

        # 회전 전 크기로 계산해도 된다. 긴 변과 토큰 수는 가로·세로를 바꿔도 같다.
        image.thumbnail(target_size(width, height))
        # thumbnail 뒤에 돌려야 원본 크기로 다 풀지 않는다.
        image = ImageOps.exif_transpose(image)
        image = _to_rgb(image)
        image.info.pop("comment", None)

        out = io.BytesIO()
        image.save(out, format="JPEG", quality=settings.JPEG_QUALITY)
        result = out.getvalue()
        final_w, final_h = image.size
    except Image.DecompressionBombError:
        return _fail("너무 큼", MSG_TOO_BIG_IMAGE)
    except Exception:
        return _fail("열 수 없음", MSG_CANNOT_OPEN)
    finally:
        image.close()

    return PreparedFile(True, "image", result, "image/jpeg", final_w, final_h, None, "")


def _to_rgb(image: Image.Image) -> Image.Image:
    has_alpha = image.mode in ("RGBA", "LA", "PA") or (image.mode == "P" and "transparency" in image.info)
    if has_alpha:
        rgba = image.convert("RGBA")
        background = Image.new("RGB", rgba.size, (255, 255, 255))
        background.paste(rgba, mask=rgba.getchannel("A"))
        return background
    if image.mode != "RGB":
        return image.convert("RGB")
    return image
