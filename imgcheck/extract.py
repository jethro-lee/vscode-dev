"""입력 파일(PDF, Office 문서, 이미지)에서 이미지를 원본 바이트 그대로 꺼낸다."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

from PIL import Image

from .models import ImageItem

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp", ".gif", ".heic", ".avif"}
OFFICE_EXTS = {".docx", ".pptx", ".xlsx", ".hwpx", ".odt", ".odp"}
MIN_SIDE = 64  # 아이콘/장식 등 너무 작은 이미지는 건너뜀


def _too_small(data: bytes) -> bool:
    try:
        with Image.open(io.BytesIO(data)) as im:
            return min(im.size) < MIN_SIDE
    except Exception:
        return True  # 열 수 없는 형식(EMF/WMF 등)은 제외


def extract_images(path: str | Path) -> list[ImageItem]:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _from_pdf(path)
    if suffix in OFFICE_EXTS:
        return _from_zip(path)
    if suffix in IMAGE_EXTS:
        ext = suffix.lstrip(".").replace("jpg", "jpeg")
        return [ImageItem(name=path.name, source=str(path), data=path.read_bytes(), ext=ext)]
    raise ValueError(f"지원하지 않는 파일 형식입니다: {path.name}")


def _from_pdf(path: Path) -> list[ImageItem]:
    import pymupdf

    items: list[ImageItem] = []
    seen: set[int] = set()
    with pymupdf.open(path) as doc:
        for page_no, page in enumerate(doc, start=1):
            for idx, img in enumerate(page.get_images(full=True), start=1):
                xref = img[0]
                if xref in seen:
                    continue
                seen.add(xref)
                info = doc.extract_image(xref)
                if not info or _too_small(info["image"]):
                    continue
                ext = info.get("ext", "png").replace("jpg", "jpeg")
                items.append(ImageItem(
                    name=f"p{page_no}_img{idx}.{ext}",
                    source=str(path),
                    data=info["image"],
                    ext=ext,
                    location=f"{page_no}페이지",
                ))
    return items


def _from_zip(path: Path) -> list[ImageItem]:
    items: list[ImageItem] = []
    with zipfile.ZipFile(path) as zf:
        for name in sorted(zf.namelist()):
            ext = Path(name).suffix.lower()
            if ext not in IMAGE_EXTS:
                continue
            data = zf.read(name)
            if _too_small(data):
                continue
            items.append(ImageItem(
                name=Path(name).name,
                source=str(path),
                data=data,
                ext=ext.lstrip(".").replace("jpg", "jpeg"),
                location=name,
            ))
    return items
