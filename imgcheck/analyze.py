from __future__ import annotations

import io

from PIL import Image, ImageOps

from .checks import ALL_CHECKS
from .models import CheckResult, ImageItem, ImageReport

Image.MAX_IMAGE_PIXELS = 200_000_000

try:  # HEIC/AVIF 지원 (설치되어 있을 때만)
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    pass


def analyze_image(item: ImageItem, checks=None) -> ImageReport:
    rep = ImageReport(item=item)
    try:
        img = Image.open(io.BytesIO(item.data))
        img.load()
        img = ImageOps.exif_transpose(img)
    except Exception as e:
        rep.error = f"이미지를 열 수 없습니다: {e}"
        return rep
    rep.width, rep.height = img.size

    for check in checks or ALL_CHECKS:
        try:
            rep.results.append(check(item, img))
        except Exception as e:  # 한 검사가 실패해도 나머지는 계속
            res = CheckResult(check.__name__, check.__name__)
            res.skipped = f"검사 중 오류: {e}"
            rep.results.append(res)
    return rep
