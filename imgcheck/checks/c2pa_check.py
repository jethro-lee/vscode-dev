"""C2PA(콘텐츠 자격증명) 매니페스트를 읽어 AI 생성/편집 이력을 확인한다."""

from __future__ import annotations

import io
import json

from PIL import Image

from ..models import CheckResult, ImageItem, Level

MIME = {
    "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp",
    "tif": "image/tiff", "tiff": "image/tiff", "heic": "image/heic", "avif": "image/avif",
}


def check_c2pa(item: ImageItem, img: Image.Image) -> CheckResult:
    r = CheckResult("c2pa", "C2PA 출처 정보 (콘텐츠 자격증명)")
    try:
        import c2pa
    except ImportError:
        r.skipped = "c2pa-python 이 설치되지 않음"
        return r

    mime = MIME.get(item.ext)
    if not mime:
        r.skipped = f"{item.ext} 형식은 C2PA 확인을 지원하지 않음"
        return r

    try:
        reader = c2pa.Reader(mime, io.BytesIO(item.data))
        store = json.loads(reader.json())
        state = reader.get_validation_state()
    except Exception:
        r.add(Level.OK, "C2PA 정보가 없습니다 (대부분의 이미지는 C2PA 정보가 없음).")
        return r

    manifests = store.get("manifests", {})
    active = manifests.get(store.get("active_manifest", ""), {})
    generator = active.get("claim_generator") or ", ".join(
        g.get("name", "") for g in active.get("claim_generator_info", []))
    r.data = {"validation_state": str(state), "claim_generator": generator}

    text = json.dumps(store).lower()
    if "trainedalgorithmicmedia" in text:
        r.add(Level.ALERT, "C2PA 기록상 AI로 생성되었거나 AI 생성 요소가 포함된 이미지입니다.")
    actions = set()
    for m in manifests.values():
        for a in m.get("assertions", []):
            if a.get("label", "").startswith("c2pa.actions"):
                for act in a.get("data", {}).get("actions", []):
                    actions.add(act.get("action", ""))
    edit_actions = actions - {"c2pa.created", "c2pa.opened", ""}
    if edit_actions:
        r.add(Level.WARN, f"C2PA 편집 이력: {', '.join(sorted(edit_actions))}")
    if generator:
        r.add(Level.INFO, f"생성/서명 프로그램: {generator}")
    if str(state).lower() not in ("valid", "trusted"):
        r.add(Level.WARN, f"C2PA 서명 검증 상태: {state} (서명 이후 변경되었거나 신뢰할 수 없는 서명일 수 있음)")
    return r
