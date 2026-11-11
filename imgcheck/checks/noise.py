"""노이즈 일관성 분석.

한 장의 사진은 보통 센서 노이즈가 전체적으로 비슷하다. 다른 사진을 합성하거나
일부를 뭉개고(스탬프/블러) 다시 그리면 그 영역의 노이즈 수준이 달라진다.
"""

from __future__ import annotations

import cv2
import numpy as np
from PIL import Image

from ..models import CheckResult, ImageItem, Level
from ._util import block_map, heatmap_overlay, largest_cluster, to_rgb

BLOCK = 32


def check_noise(item: ImageItem, img: Image.Image) -> CheckResult:
    r = CheckResult("noise", "노이즈 일관성 (합성/덧칠 탐지)")
    rgb = to_rgb(img)
    gray = np.asarray(rgb.convert("L"), dtype=np.float32)
    if min(gray.shape) < BLOCK * 4:
        r.skipped = "이미지가 너무 작음"
        return r

    residual = gray - cv2.medianBlur(gray.astype(np.uint8), 3).astype(np.float32)
    noise = np.sqrt(block_map(residual ** 2, BLOCK))

    # 노이즈는 무늬가 많은 곳에서 크게 나오므로, 무늬가 적은(평탄한) 칸끼리만 비교한다
    bright = block_map(gray, BLOCK)
    smooth = cv2.GaussianBlur(gray, (0, 0), 2.0)
    gx, gy = np.gradient(smooth)
    structure = block_map(np.hypot(gx, gy), BLOCK)
    valid = (bright > 8) & (bright < 247)
    if valid.sum() < 16:
        r.skipped = "분석할 영역이 부족함"
        return r
    mask = valid & (structure <= np.percentile(structure[valid], 50))
    vals = noise[mask]
    if vals.size < 16:
        r.skipped = "분석할 영역이 부족함"
        return r

    med = float(np.median(vals))
    # 주변보다 노이즈가 비정상적으로 "낮은" 영역(뭉개기/AI 덧칠)과 "높은" 영역을 모두 본다
    low = mask & (noise < med * 0.4)
    high = mask & (noise > med * 2.5)
    low_c, high_c = largest_cluster(low), largest_cluster(high)
    r.data = {"median_noise": round(med, 3), "low_cluster": low_c, "high_cluster": high_c,
              "compared_blocks": int(mask.sum())}
    r.visual = heatmap_overlay(rgb, noise, low | high)

    if med < 0.6:
        r.add(Level.INFO, "이미지 전체 노이즈가 매우 낮습니다. 그래픽/스크린샷이거나, 강한 보정 또는 "
                          "AI 생성 이미지일 수 있습니다 (약한 신호).")

    total = int(mask.sum())
    if low_c >= max(10, total * 0.025) and low_c < total * 0.5:
        r.add(Level.WARN, f"주변보다 노이즈가 훨씬 적은 영역이 있습니다 ({low_c}칸). "
                          "지우기/복제 도장/AI 덧칠 등이 의심되지만, 초점이 나간 배경도 이렇게 보일 수 있습니다.")
    if high_c >= max(15, total * 0.08) and high_c < total * 0.5:
        r.add(Level.WARN, f"주변보다 노이즈가 훨씬 많은 영역이 있습니다 ({high_c}칸). "
                          "다른 이미지를 합성한 흔적일 수 있으나 복잡한 무늬도 이렇게 보일 수 있습니다.")
    if not r.findings:
        r.add(Level.OK, "노이즈 수준이 이미지 전체에서 비교적 일정합니다.")
    return r
