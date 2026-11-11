"""복제-이동(Copy-Move) 탐지.

같은 이미지 안에서 한 부분을 복사해 다른 곳에 붙이면(물체 복제, 지우기용 도장 등)
똑같은 특징점 무리가 "같은 방향·같은 거리"만큼 떨어져 나타난다.
"""

from __future__ import annotations

from collections import defaultdict

import cv2
import numpy as np
from PIL import Image

from ..models import CheckResult, ImageItem, Level
from ._util import to_rgb

MIN_DIST = 40      # 너무 가까운 특징점끼리는 같은 물체로 보고 무시
BIN = 8            # 이동 벡터를 묶는 단위(픽셀)
WARN_AT = 10
ALERT_AT = 25


def check_copymove(item: ImageItem, img: Image.Image) -> CheckResult:
    r = CheckResult("copymove", "복제-이동 탐지 (같은 이미지 내 복사·붙여넣기)")
    rgb = to_rgb(img, max_side=1600)
    gray = cv2.cvtColor(np.array(rgb), cv2.COLOR_RGB2GRAY)

    sift = cv2.SIFT_create(nfeatures=4000)
    kps, desc = sift.detectAndCompute(gray, None)
    if desc is None or len(kps) < 20:
        r.add(Level.OK, "특징점이 적어 복제 영역을 찾지 못했습니다 (단순한 그림/그래픽일 수 있음).")
        return r

    matcher = cv2.BFMatcher(cv2.NORM_L2)
    knn = matcher.knnMatch(desc, desc, k=3)

    groups: dict[tuple[int, int], list[tuple[tuple[float, float], tuple[float, float]]]] = defaultdict(list)
    for m in knn:
        if len(m) < 3:
            continue
        # m[0]은 자기 자신. m[1]이 m[2]보다 확실히 가까울 때만 채택(비율 검사)
        best, second = m[1], m[2]
        if best.distance > 0.6 * second.distance:
            continue
        p1 = np.array(kps[best.queryIdx].pt)
        p2 = np.array(kps[best.trainIdx].pt)
        d = p2 - p1
        if np.hypot(*d) < MIN_DIST:
            continue
        # 방향을 통일해 A→B 와 B→A 를 같은 묶음으로 본다
        if d[0] < 0 or (d[0] == 0 and d[1] < 0):
            d, p1, p2 = -d, p2, p1
        key = (int(round(d[0] / BIN)), int(round(d[1] / BIN)))
        groups[key].append((tuple(p1), tuple(p2)))

    # 서로 다른 출발점만 센다 (같은 매칭이 양방향으로 두 번 들어가는 것 방지)
    clusters = sorted(
        ((k, list({p1: (p1, p2) for p1, p2 in v}.values())) for k, v in groups.items()),
        key=lambda kv: len(kv[1]), reverse=True,
    )
    top = len(clusters[0][1]) if clusters else 0
    r.data = {"keypoints": len(kps), "largest_group": top}

    if top >= WARN_AT:
        vis = np.array(rgb).copy()
        colors = [(255, 0, 0), (255, 160, 0), (0, 200, 255)]
        for (key, pairs), color in zip(clusters[:3], colors):
            if len(pairs) < WARN_AT:
                break
            for p1, p2 in pairs:
                a = tuple(int(v) for v in p1)
                b = tuple(int(v) for v in p2)
                cv2.line(vis, a, b, color, 1, cv2.LINE_AA)
                cv2.circle(vis, a, 4, color, 2)
                cv2.circle(vis, b, 4, color, 2)
        r.visual = Image.fromarray(vis)
        level = Level.ALERT if top >= ALERT_AT else Level.WARN
        r.add(level, f"같은 모양이 일정한 거리만큼 떨어져 반복되는 부분이 있습니다 (일치점 {top}개). "
                     "복사·붙여넣기 흔적일 수 있습니다. 단, 타일·창문·글자처럼 원래 반복되는 무늬도 "
                     "이렇게 나오므로 선으로 연결된 부분을 눈으로 확인하세요.")
    else:
        r.add(Level.OK, "이미지 안에서 복사·붙여넣기된 영역은 발견되지 않았습니다.")
    return r
