"""분석 결과를 HTML 한 파일(이미지 포함)과 JSON으로 저장한다."""

from __future__ import annotations

import base64
import html
import io
import json
from datetime import datetime
from pathlib import Path

from PIL import Image

from . import __version__
from .models import ImageReport, Level

THUMB = 900

CSS = """
:root{--bg:#f6f7f9;--card:#fff;--text:#1d2129;--muted:#6b7280;--line:#e5e7eb;
--ok:#15803d;--info:#2563eb;--warn:#b45309;--alert:#b91c1c}
@media (prefers-color-scheme:dark){:root{--bg:#111318;--card:#1b1e25;--text:#e6e8ec;
--muted:#9aa1ad;--line:#2c313a;--ok:#4ade80;--info:#60a5fa;--warn:#fbbf24;--alert:#f87171}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);
font:15px/1.6 -apple-system,"Apple SD Gothic Neo","Malgun Gothic",sans-serif}
main{max-width:1000px;margin:0 auto;padding:24px 16px}
h1{font-size:22px;margin:0 0 4px}h2{font-size:17px;margin:0}
.muted{color:var(--muted);font-size:13px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px;margin:16px 0}
.notice{border-left:4px solid var(--warn)}
table{width:100%;border-collapse:collapse;font-size:14px}
td,th{padding:6px 8px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
.badge{display:inline-block;padding:1px 8px;border-radius:99px;font-size:12px;font-weight:600;
border:1px solid currentColor;white-space:nowrap}
.l0{color:var(--ok)}.l1{color:var(--info)}.l2{color:var(--warn)}.l3{color:var(--alert)}
img{max-width:100%;height:auto;border-radius:6px;border:1px solid var(--line)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px}
details{margin-top:10px}summary{cursor:pointer;font-weight:600}
ul{margin:6px 0;padding-left:20px}
pre{white-space:pre-wrap;word-break:break-all;font-size:12px;background:var(--bg);padding:8px;border-radius:6px}
"""


def _img_b64(img: Image.Image) -> str:
    img = img.convert("RGB")
    img.thumbnail((THUMB, THUMB))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def _badge(level: Level) -> str:
    return f'<span class="badge l{int(level)}">{level.label}</span>'


def _image_section(i: int, rep: ImageReport) -> str:
    it = rep.item
    e = html.escape
    out = [f'<section class="card" id="img{i}">']
    out.append(f"<h2>{i}. {e(it.name)} {_badge(rep.level)}</h2>")
    meta = f"{e(it.location)} · " if it.location else ""
    out.append(f'<div class="muted">{meta}{rep.width}x{rep.height} · {it.ext.upper()} · '
               f"{len(it.data) // 1024}KB</div>")
    if rep.error:
        out.append(f"<p>{e(rep.error)}</p></section>")
        return "".join(out)
    out.append(f"<p><b>판정: {e(rep.verdict)}</b></p>")

    try:
        orig = Image.open(io.BytesIO(it.data))
        out.append(f'<img src="{_img_b64(orig)}" alt="원본">')
    except Exception:
        pass

    for res in rep.results:
        out.append(f"<details {'open' if res.level >= Level.WARN else ''}>")
        status = "건너뜀" if res.skipped else res.level.label
        cls = "l1" if res.skipped else f"l{int(res.level)}"
        out.append(f'<summary>{e(res.title)} <span class="badge {cls}">{status}</span></summary>')
        if res.skipped:
            out.append(f'<p class="muted">{e(res.skipped)}</p>')
        if res.findings:
            out.append("<ul>")
            for f in sorted(res.findings, key=lambda f: -f.level):
                out.append(f"<li>{_badge(f.level)} {e(f.message)}</li>")
            out.append("</ul>")
        if res.visual is not None:
            out.append(f'<img src="{_img_b64(res.visual)}" alt="{e(res.title)} 시각화">')
        if res.data:
            out.append(f"<pre>{e(json.dumps(res.data, ensure_ascii=False, indent=2))}</pre>")
        out.append("</details>")
    out.append("</section>")
    return "".join(out)


def write_html(reports: list[ImageReport], sources: list[str], path: str | Path) -> None:
    e = html.escape
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    counts = {lv: sum(1 for r in reports if r.level == lv) for lv in Level}

    rows = "".join(
        f'<tr><td><a href="#img{i}">{i}</a></td><td>{e(r.item.name)}</td>'
        f"<td>{e(r.item.location)}</td><td>{_badge(r.level)} {e(r.verdict)}</td></tr>"
        for i, r in enumerate(reports, start=1))

    body = f"""
<h1>이미지 진위 분석 리포트</h1>
<div class="muted">분석 대상: {e(', '.join(Path(s).name for s in sources))} · {now} · imgcheck {__version__}</div>

<div class="card">
<b>요약</b> — 이미지 {len(reports)}개:
{_badge(Level.ALERT)} {counts[Level.ALERT]} &nbsp;
{_badge(Level.WARN)} {counts[Level.WARN]} &nbsp;
{_badge(Level.INFO)} {counts[Level.INFO]} &nbsp;
{_badge(Level.OK)} {counts[Level.OK]}
<table style="margin-top:10px"><tr><th>#</th><th>이미지</th><th>위치</th><th>판정</th></tr>{rows}</table>
</div>

<div class="card notice">
<b>해석 시 주의</b>
<ul>
<li>이 리포트는 조작·AI 생성의 <b>의심 신호</b>를 보여줄 뿐, 진위를 확정하지 않습니다.</li>
<li>'특이사항 없음'은 "이 검사들로는 흔적을 찾지 못했다"는 뜻이지 진본 보증이 아닙니다.</li>
<li>문서(PDF/Word)에 넣은 이미지는 메타데이터가 지워지거나 재압축되는 경우가 많아, 가능하면 원본 파일로 다시 검사하세요.</li>
<li>법적 분쟁 등 중요한 사안은 전문 디지털 포렌식 감정을 권합니다.</li>
</ul>
</div>
{''.join(_image_section(i, r) for i, r in enumerate(reports, start=1))}
"""
    page = (f'<!doctype html><html lang="ko"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f"<title>이미지 진위 분석</title><style>{CSS}</style></head>"
            f"<body><main>{body}</main></body></html>")
    Path(path).write_text(page, encoding="utf-8")


def write_json(reports: list[ImageReport], path: str | Path) -> None:
    data = []
    for r in reports:
        data.append({
            "name": r.item.name, "source": r.item.source, "location": r.item.location,
            "width": r.width, "height": r.height, "level": r.level.name, "verdict": r.verdict,
            "error": r.error,
            "checks": [{
                "name": c.name, "level": c.level.name, "skipped": c.skipped,
                "findings": [{"level": f.level.name, "message": f.message} for f in c.findings],
                "data": c.data,
            } for c in r.results],
        })
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
