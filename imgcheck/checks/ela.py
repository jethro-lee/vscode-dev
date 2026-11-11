"""ELA(Error Level Analysis, 압축 오류 분석).

JPEG를 같은 품질로 다시 저장하면, 원래 함께 압축된 영역은 차이가 비슷하게 나오고
나중에 붙여 넣거나 고친 영역은 차이가 다르게 나오는 경향이 있다.
"""

from __future__ import annotations

import io

import numpy as np
from PIL import Image, ImageChops

from ..models import CheckResult, ImageItem, Level
from ._util import block_map, heatmap_overlay, largest_cluster, outlier_ratio, to_rgb

ELA_BLOCK = 16
QUALITY = 90


def check_ela(item: ImageItem, img: Image.Image) -> CheckResult:
    r = CheckResult("ela", "ELA 압축 오류 분석 (부분 편집 탐지)")
    rgb = to_rgb(img)

    buf = io.BytesIO()
    rgb.save(buf, "JPEG", quality=QUALITY)
    resaved = Image.open(io.BytesIO(buf.getvalue()))
    diff = np.asarray(ImageChops.difference(rgb, resaved), dtype=np.float32).max(axis=2)

    blocks = block_map(diff, ELA_BLOCK)
    # 완전히 평평한 영역(하늘, 흰 배경)은 원래 차이가 작으므로 판단에서 뺀다
    gray = np.asarray(rgb.convert("L"), dtype=np.float32)
    texture = block_map(np.abs(np.diff(gray, axis=1, append=gray[:, -1:])), ELA_BLOCK)
    mask = texture > 1.0

    ratio, out = outlier_ratio(blocks, mask, z=5.0)
    cluster = largest_cluster(out)
    r.data = {"outlier_ratio": round(ratio, 4), "largest_cluster_blocks": cluster,
              "mean_error": round(float(diff.mean()), 3)}

    # 사람이 보기 쉽게 차이를 증폭한 ELA 이미지 대신, 원본 위 히트맵을 보여준다
    r.visual = heatmap_overlay(rgb, blocks, out)

    if item.ext != "jpeg":
        r.add(Level.INFO, f"{item.ext.upper()} 이미지라 ELA 신뢰도가 낮습니다 (JPEG에서 가장 잘 동작).")

    # 튀는 칸이 이미지 일부에만 한 덩어리로 몰려 있을 때만 경고한다
    n_valid = max(int(mask.sum()), 1)
    if cluster >= max(12, n_valid * 0.015) and ratio < 0.1:
        r.add(Level.WARN, f"압축 오류가 주변과 다른 영역이 한 덩어리로 있습니다 ({cluster}칸). "
                          "히트맵의 빨간 테두리 영역을 눈으로 확인하세요. 글자, 경계선, 강한 대비 영역은 "
                          "원래도 밝게 나올 수 있습니다.")
    elif ratio >= 0.1:
        r.add(Level.INFO, "이미지 전체에 압축 오류가 고르게 높습니다. 여러 번 재압축되었거나 "
                          "텍스처가 많은 이미지로 보입니다.")
    else:
        r.add(Level.OK, "압축 오류가 이미지 전체에서 비교적 고르게 나타납니다.")
    return r
