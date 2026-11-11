"""(선택) 외부 AI 생성 판별 API 연동.

환경변수 SIGHTENGINE_API_USER, SIGHTENGINE_API_SECRET 이 설정되어 있을 때만 동작한다.
설정하지 않으면 이 검사는 건너뛰며, 이미지가 외부로 전송되지 않는다.
"""

from __future__ import annotations

import json
import os
import urllib.request
import uuid

from PIL import Image

from ..models import CheckResult, ImageItem, Level

URL = "https://api.sightengine.com/1.0/check.json"


def _multipart(fields: dict[str, str], file_bytes: bytes, filename: str) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    parts = []
    for k, v in fields.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    parts.append(
        f'--{boundary}\r\nContent-Disposition: form-data; name="media"; filename="{filename}"\r\n'
        f"Content-Type: application/octet-stream\r\n\r\n".encode() + file_bytes + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def check_ai_api(item: ImageItem, img: Image.Image) -> CheckResult:
    r = CheckResult("ai_api", "AI 생성 판별 (외부 API)")
    user = os.environ.get("SIGHTENGINE_API_USER")
    secret = os.environ.get("SIGHTENGINE_API_SECRET")
    if not (user and secret):
        r.skipped = "API 키 미설정 (README의 'AI 판별 API 연동' 참고)"
        return r

    body, ctype = _multipart({"models": "genai", "api_user": user, "api_secret": secret},
                             item.data, item.name)
    req = urllib.request.Request(URL, data=body, headers={"Content-Type": ctype}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            res = json.load(resp)
    except Exception as e:
        r.skipped = f"API 호출 실패: {e}"
        return r

    if res.get("status") != "success":
        r.skipped = f"API 오류: {res.get('error', res)}"
        return r

    score = float(res.get("type", {}).get("ai_generated", 0.0))
    r.data = {"ai_generated": score}
    pct = f"{score * 100:.0f}%"
    if score >= 0.85:
        r.add(Level.ALERT, f"AI 생성 가능성이 높게 나왔습니다 ({pct}).")
    elif score >= 0.5:
        r.add(Level.WARN, f"AI 생성 가능성이 중간 정도로 나왔습니다 ({pct}).")
    else:
        r.add(Level.OK, f"AI 생성 가능성이 낮게 나왔습니다 ({pct}).")
    r.add(Level.INFO, "판별 모델 결과는 확률이며 오탐·미탐이 있을 수 있습니다.")
    return r
