"""EXIF / XMP / PNG 텍스트 등 메타데이터에서 AI 생성·편집 흔적을 찾는다."""

from __future__ import annotations

import io
import re

from PIL import ExifTags, Image

from ..models import CheckResult, ImageItem, Level

AI_KEYWORDS = [
    "midjourney", "stable diffusion", "stablediffusion", "sdxl", "dall-e", "dall·e", "dalle",
    "openai", "chatgpt", "gpt-4o", "sora", "firefly", "imagen", "gemini", "nano banana",
    "comfyui", "automatic1111", "invokeai", "novelai", "leonardo.ai", "ideogram",
    "black forest labs", "bing image creator", "microsoft designer", "grok",
    "trainedalgorithmicmedia", "compositewithtrainedalgorithmicmedia",
    "algorithmicmedia", "generative fill", "made with ai", "ai generated",
]

EDIT_KEYWORDS = [
    "photoshop", "lightroom", "gimp", "affinity", "pixelmator", "snapseed", "picsart",
    "canva", "facetune", "meitu", "photoscape", "paint.net", "corel", "capture one",
    "luminar", "fotor", "remini", "lensa",
]

# PNG 텍스트 청크에 생성 정보를 남기는 도구들의 키
AI_PNG_KEYS = {"parameters", "prompt", "workflow", "sd-metadata", "dream", "invokeai_metadata"}

# 이미지 생성 모델에서 흔한 해상도 (약한 신호)
AI_TYPICAL_SIZES = {
    (512, 512), (768, 768), (1024, 1024), (2048, 2048),
    (1024, 1792), (1792, 1024), (1024, 1536), (1536, 1024),
    (832, 1216), (1216, 832), (896, 1152), (1152, 896), (768, 1344), (1344, 768),
    (640, 1536), (1536, 640), (1456, 816), (816, 1456), (1344, 896), (896, 1344),
}


def _find(keywords: list[str], text: str) -> list[str]:
    t = text.lower()
    hits = []
    for k in keywords:
        # 짧은 단어(flux, grok 등)는 단어 경계로만 매칭해 오탐을 줄인다
        if re.search(rf"(?<![a-z]){re.escape(k)}(?![a-z])", t):
            hits.append(k)
    return hits


def check_metadata(item: ImageItem, img: Image.Image) -> CheckResult:
    r = CheckResult("metadata", "메타데이터 (EXIF/XMP)")

    with Image.open(io.BytesIO(item.data)) as raw:
        exif = raw.getexif()
        info = dict(raw.info)

    tags: dict[str, str] = {}
    for tag_id, value in exif.items():
        tags[ExifTags.TAGS.get(tag_id, str(tag_id))] = str(value)
    try:
        for tag_id, value in exif.get_ifd(ExifTags.IFD.Exif).items():
            tags[ExifTags.TAGS.get(tag_id, str(tag_id))] = str(value)
    except Exception:
        pass

    xmp = info.get("xmp") or info.get("XML:com.adobe.xmp") or b""
    if isinstance(xmp, bytes):
        xmp = xmp.decode("utf-8", "ignore")

    png_text = {k: str(v) for k, v in info.items()
                if isinstance(v, str) and k not in ("xmp", "XML:com.adobe.xmp")}

    keep = ["Make", "Model", "Software", "DateTime", "DateTimeOriginal",
            "DateTimeDigitized", "Artist", "ImageDescription", "LensModel"]
    r.data = {
        "exif": {k: tags[k][:200] for k in keep if k in tags},
        "has_xmp": bool(xmp),
        "png_text_keys": sorted(png_text.keys()),
    }

    all_text = " ".join(tags.values()) + " " + xmp + " " + " ".join(
        f"{k} {v}" for k, v in png_text.items())

    ai_hits = _find(AI_KEYWORDS, all_text)
    ai_png = AI_PNG_KEYS & {k.lower() for k in png_text}
    if ai_hits:
        r.add(Level.ALERT, f"AI 생성 도구 흔적이 메타데이터에 있습니다: {', '.join(ai_hits)}")
    if ai_png:
        r.add(Level.ALERT, f"AI 생성 프로그램이 남기는 PNG 정보(프롬프트 등)가 있습니다: {', '.join(sorted(ai_png))}")

    edit_hits = _find(EDIT_KEYWORDS, all_text)
    if edit_hits:
        r.add(Level.WARN, f"편집 프로그램 흔적이 있습니다: {', '.join(edit_hits)} "
                          "(밝기 보정 같은 단순 편집일 수도 있음)")

    if "Make" in tags or "Model" in tags:
        cam = f"{tags.get('Make', '').strip()} {tags.get('Model', '').strip()}".strip()
        r.add(Level.OK, f"카메라 정보 있음: {cam}")
    else:
        r.add(Level.INFO, "카메라 정보가 없습니다. 메타데이터는 문서에 넣거나 메신저로 보낼 때 "
                          "흔히 지워지므로 이것만으로 조작을 뜻하지는 않습니다.")

    orig, mod = tags.get("DateTimeOriginal"), tags.get("DateTime")
    if orig and mod and orig != mod:
        r.add(Level.INFO, f"촬영 시각({orig})과 수정 시각({mod})이 다릅니다.")

    if img.size in AI_TYPICAL_SIZES and "Make" not in tags:
        r.add(Level.INFO, f"해상도 {img.size[0]}x{img.size[1]}는 AI 이미지 생성기에서 흔한 크기입니다 (약한 신호).")

    return r
