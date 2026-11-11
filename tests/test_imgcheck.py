import io
import json

import numpy as np
import pymupdf
import pytest
from PIL import Image, PngImagePlugin

from imgcheck.__main__ import main
from imgcheck.analyze import analyze_image
from imgcheck.extract import extract_images
from imgcheck.models import ImageItem, Level


def _photo(seed=0, size=(800, 600)) -> Image.Image:
    """사진과 비슷한 합성 이미지: 부드러운 그라데이션 + 도형 + 센서 노이즈."""
    rng = np.random.default_rng(seed)
    w, h = size
    y, x = np.mgrid[0:h, 0:w]
    base = np.stack([x / w * 180 + 40, y / h * 160 + 50, (x + y) / (w + h) * 120 + 60], axis=2)
    for _ in range(25):
        cx, cy, r = rng.integers(0, w), rng.integers(0, h), rng.integers(10, 60)
        base[(x - cx) ** 2 + (y - cy) ** 2 < r * r] = rng.integers(0, 255, 3)
    base += rng.normal(0, 3, base.shape)
    return Image.fromarray(np.clip(base, 0, 255).astype(np.uint8))


def _jpeg(img: Image.Image, **kw) -> bytes:
    b = io.BytesIO()
    img.save(b, "JPEG", quality=90, **kw)
    return b.getvalue()


def _levels(rep):
    return {r.name: r.level for r in rep.results}


def test_camera_exif_is_ok():
    ex = Image.Exif()
    ex[271], ex[272] = "Canon", "EOS R6"
    rep = analyze_image(ImageItem("a.jpg", "x", _jpeg(_photo(), exif=ex), "jpeg"))
    assert _levels(rep)["metadata"] == Level.OK
    assert rep.results[0].data["exif"]["Make"] == "Canon"


def test_ai_png_metadata_alert():
    info = PngImagePlugin.PngInfo()
    info.add_text("parameters", "a cat, Steps: 30, Model: sdxl")
    b = io.BytesIO()
    _photo().save(b, "PNG", pnginfo=info)
    rep = analyze_image(ImageItem("ai.png", "x", b.getvalue(), "png"))
    assert _levels(rep)["metadata"] == Level.ALERT
    assert rep.level == Level.ALERT


def test_editor_software_warn():
    ex = Image.Exif()
    ex[305] = "Adobe Photoshop 25.0"
    rep = analyze_image(ImageItem("e.jpg", "x", _jpeg(_photo(), exif=ex), "jpeg"))
    assert _levels(rep)["metadata"] == Level.WARN


def test_copy_move_detected():
    a = np.array(_photo(seed=1))
    rng = np.random.default_rng(5)
    patch = rng.integers(0, 255, (120, 160, 3), dtype=np.uint8)  # 특징점이 많은 영역
    a[50:170, 50:210] = patch
    a[380:500, 550:710] = patch  # 같은 영역을 다른 곳에 복사
    rep = analyze_image(ImageItem("cm.jpg", "x", _jpeg(Image.fromarray(a)), "jpeg"))
    cm = next(r for r in rep.results if r.name == "copymove")
    assert cm.level >= Level.WARN
    assert cm.visual is not None


def test_clean_image_has_no_copy_move():
    rep = analyze_image(ImageItem("c.jpg", "x", _jpeg(_photo(seed=2)), "jpeg"))
    assert _levels(rep)["copymove"] == Level.OK


def test_ai_api_skipped_without_keys(monkeypatch):
    monkeypatch.delenv("SIGHTENGINE_API_USER", raising=False)
    rep = analyze_image(ImageItem("c.jpg", "x", _jpeg(_photo()), "jpeg"))
    api = next(r for r in rep.results if r.name == "ai_api")
    assert api.skipped


def test_pdf_extraction_keeps_original_bytes(tmp_path):
    data = _jpeg(_photo())
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_image(page.rect, stream=data)
    pdf = tmp_path / "doc.pdf"
    doc.save(pdf)
    items = extract_images(pdf)
    assert len(items) == 1
    assert items[0].location == "1페이지"
    assert items[0].data == data  # 재인코딩 없이 원본 그대로


def test_unsupported_file(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("x")
    with pytest.raises(ValueError):
        extract_images(f)


def test_cli_writes_reports(tmp_path):
    img = tmp_path / "p.jpg"
    img.write_bytes(_jpeg(_photo()))
    html_out, json_out = tmp_path / "r.html", tmp_path / "r.json"
    code = main([str(img), "-o", str(html_out), "--json", str(json_out)])
    assert code in (0, 2, 3)
    assert "이미지 진위 분석 리포트" in html_out.read_text(encoding="utf-8")
    assert json.loads(json_out.read_text(encoding="utf-8"))[0]["name"] == "p.jpg"
