from __future__ import annotations

import cv2
import numpy as np
from PIL import Image

MAX_SIDE = 3000  # 너무 큰 이미지는 분석 속도를 위해 줄인다


def to_rgb(img: Image.Image, max_side: int = MAX_SIDE) -> Image.Image:
    img = img.convert("RGB")
    if max(img.size) > max_side:
        img = img.copy()
        img.thumbnail((max_side, max_side), Image.LANCZOS)
    return img


def block_map(values: np.ndarray, block: int) -> np.ndarray:
    """2차원 배열을 block x block 칸 단위 평균으로 줄인다."""
    h, w = values.shape
    h2, w2 = h // block, w // block
    v = values[: h2 * block, : w2 * block]
    return v.reshape(h2, block, w2, block).mean(axis=(1, 3))


def outlier_ratio(blocks: np.ndarray, mask: np.ndarray | None = None, z: float = 4.0) -> tuple[float, np.ndarray]:
    """중앙값/MAD 기준으로 튀는 칸의 비율과 위치를 구한다."""
    vals = blocks[mask] if mask is not None else blocks.ravel()
    if vals.size < 16:
        return 0.0, np.zeros_like(blocks, dtype=bool)
    med = np.median(vals)
    mad = np.median(np.abs(vals - med)) * 1.4826 + 1e-6
    out = (blocks - med) / mad > z
    if mask is not None:
        out &= mask
    return float(out.sum()) / vals.size, out


def heatmap_overlay(base: Image.Image, values: np.ndarray, outliers: np.ndarray | None = None) -> Image.Image:
    """값 배열을 컬러 히트맵으로 만들어 원본 위에 겹친다. 튀는 칸은 빨간 테두리로 표시."""
    base_np = np.array(base.convert("RGB"))
    h, w = base_np.shape[:2]
    v = values.astype(np.float32)
    hi = np.percentile(v, 99.5) or 1.0
    v = np.clip(v / hi, 0, 1)
    heat = cv2.applyColorMap((v * 255).astype(np.uint8), cv2.COLORMAP_JET)
    heat = cv2.resize(heat, (w, h), interpolation=cv2.INTER_NEAREST)
    heat = cv2.cvtColor(heat, cv2.COLOR_BGR2RGB)
    out = cv2.addWeighted(base_np, 0.45, heat, 0.55, 0)
    if outliers is not None and outliers.any():
        bh, bw = h / outliers.shape[0], w / outliers.shape[1]
        for y, x in zip(*np.nonzero(outliers)):
            cv2.rectangle(out, (int(x * bw), int(y * bh)), (int((x + 1) * bw), int((y + 1) * bh)), (255, 0, 0), 2)
    return Image.fromarray(out)


def largest_cluster(outliers: np.ndarray) -> int:
    """튀는 칸 중 서로 붙어 있는 가장 큰 덩어리의 칸 수."""
    if not outliers.any():
        return 0
    n, labels, stats, _ = cv2.connectedComponentsWithStats(outliers.astype(np.uint8), connectivity=8)
    return int(stats[1:, cv2.CC_STAT_AREA].max()) if n > 1 else 0
