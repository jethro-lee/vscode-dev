"""imgcheck 모듈 소스를 그대로 셀로 옮겨 단독 실행 가능한 노트북을 만든다."""
import json, re, sys
from pathlib import Path

ROOT = Path(sys.argv[1]); OUT = Path(sys.argv[2])

def src(rel):
    s = (ROOT / "imgcheck" / rel).read_text(encoding="utf-8")
    s = "\n".join(l for l in s.splitlines() if not l.startswith("from ."))
    return s.strip() + "\n"

cells = []
def md(t): cells.append({"cell_type": "markdown", "metadata": {}, "source": t.strip("\n")})
def code(t): cells.append({"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [], "source": t.strip("\n")})

md("""
# 사진 조작·AI 생성 의심 신호 검사 (폴더 단위)

`D:\\data` 폴더 안의 사진(및 PDF·Word 등 문서 속 이미지)을 모두 검사해 **조작 또는 AI 생성이 의심되는 신호**를 찾습니다.

**사용법**: 위에서부터 셀을 순서대로 실행하세요 (메뉴 `Run > Run All Cells`). 설정은 **2번 셀**만 바꾸면 됩니다.

| 검사 | 찾는 것 |
|---|---|
| 메타데이터 | AI 생성기 이름·프롬프트, Photoshop 등 편집 프로그램, 카메라 정보 |
| C2PA | 콘텐츠 자격증명에 기록된 AI 생성·편집 이력 |
| ELA | 나중에 붙여 넣거나 고친 영역 (JPEG에서 정확) |
| 노이즈 | 합성된 영역, 지우기·뭉개기·AI 덧칠 |
| 복제-이동 | 같은 사진 안에서 복사·붙여넣기한 부분 |
| AI 판별 API | (선택) 외부 모델의 AI 생성 확률 |

> ⚠️ 이 검사는 진위를 **확정하지 않습니다**. `의심`/`주의`는 사람이 표시된 영역을 직접 확인하라는 뜻이고, `정상`은 "이 검사로는 흔적을 못 찾았다"는 뜻입니다.
""")

md("## 1. 패키지 설치 (처음 한 번만)")
code("%pip install -q pillow numpy opencv-python-headless pymupdf c2pa-python pandas matplotlib\n# 아이폰 HEIC 사진이 있다면 아래 줄의 주석을 풀고 실행\n# %pip install -q pillow-heif")

md("## 2. 설정")
code(r'''
from pathlib import Path
import os

DATA_DIR = Path(r"D:\data")   # 검사할 폴더
RECURSIVE = True               # 하위 폴더까지 검사
INCLUDE_DOCS = True            # PDF/DOCX/PPTX 안의 이미지도 검사
SHOW_LEVEL = "주의"            # 4번 셀에서 그림까지 보여줄 최소 수준: "의심" / "주의" / "참고" / "정상"

REPORT_PATH = DATA_DIR / "imgcheck_report.html"   # HTML 리포트 저장 위치
CSV_PATH = DATA_DIR / "imgcheck_result.csv"       # 엑셀로 열 수 있는 결과표

# (선택) Sightengine AI 판별 API 키. 비워두면 사진이 외부로 전송되지 않습니다.
SIGHTENGINE_API_USER = ""
SIGHTENGINE_API_SECRET = ""

if SIGHTENGINE_API_USER and SIGHTENGINE_API_SECRET:
    os.environ["SIGHTENGINE_API_USER"] = SIGHTENGINE_API_USER
    os.environ["SIGHTENGINE_API_SECRET"] = SIGHTENGINE_API_SECRET

assert DATA_DIR.exists(), f"폴더가 없습니다: {DATA_DIR}"
print("검사 폴더:", DATA_DIR)
''')

md("## 3. 검사 코드 정의\n아래 셀들은 수정할 필요 없이 실행만 하면 됩니다.")
code('__version__ = "0.1.0"\n\n' + src("models.py"))
code(src("checks/_util.py"))
code(src("extract.py"))
code(src("checks/metadata.py"))
code(src("checks/c2pa_check.py"))
code(src("checks/ela.py"))
code(src("checks/noise.py"))
code(src("checks/copymove.py"))
code(src("checks/ai_api.py"))
code("ALL_CHECKS = [check_metadata, check_c2pa, check_ela, check_noise, check_copymove, check_ai_api]\n\n" + src("analyze.py"))
code(src("report.py"))

md("## 4. 폴더 검사 실행")
code(r'''
import time

pattern = "**/*" if RECURSIVE else "*"
exts = set(IMAGE_EXTS) | ({".pdf"} | OFFICE_EXTS if INCLUDE_DOCS else set())
files = sorted(p for p in DATA_DIR.glob(pattern) if p.is_file() and p.suffix.lower() in exts)
print(f"대상 파일 {len(files)}개")

items = []
for f in files:
    try:
        found = extract_images(f)
    except Exception as e:
        print(f"  [건너뜀] {f.name}: {e}")
        continue
    rel = str(f.relative_to(DATA_DIR))
    for it in found:
        it.name = rel if f.suffix.lower() in IMAGE_EXTS else f"{rel} :: {it.name}"
    items.extend(found)
print(f"검사할 이미지 {len(items)}개\n")

reports = []
t0 = time.time()
for n, it in enumerate(items, start=1):
    rep = analyze_image(it)
    reports.append(rep)
    print(f"[{n}/{len(items)}] {rep.level.label:>2} | {it.name}")
print(f"\n완료: {time.time() - t0:.1f}초")
''')

md("## 5. 결과 요약표\n의심 → 주의 → 참고 → 정상 순으로 정렬됩니다.")
code(r'''
import pandas as pd
pd.set_option("display.max_colwidth", 120)

SHORT = {"metadata": "메타데이터", "c2pa": "C2PA", "ela": "ELA", "noise": "노이즈",
         "copymove": "복제", "ai_api": "AI판별"}

rows = []
for r in reports:
    row = {"판정": r.level.label, "파일": r.item.name, "크기": f"{r.width}x{r.height}"}
    for res in r.results:
        row[SHORT.get(res.name, res.name)] = "건너뜀" if res.skipped else res.level.label
    row["주요 신호"] = " / ".join(f.message for res in r.results for f in res.findings
                                if f.level >= Level.WARN) or r.error or ""
    row["_lv"] = int(r.level)
    rows.append(row)

df = pd.DataFrame(rows).sort_values(["_lv", "파일"], ascending=[False, True]).drop(columns="_lv")
print(df["판정"].value_counts().to_string())
df.reset_index(drop=True)
''')

md("## 6. 의심 사진 자세히 보기\n원본과 함께, 의심 영역을 표시한 그림(빨간 테두리·선)을 보여줍니다.")
code(r'''
import io, platform
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image

if platform.system() == "Windows":
    plt.rcParams["font.family"] = "Malgun Gothic"
elif platform.system() == "Darwin":
    plt.rcParams["font.family"] = "AppleGothic"
plt.rcParams["axes.unicode_minus"] = False

LEVEL_BY_LABEL = {lv.label: lv for lv in Level}


def show_report(r, only_flagged=True):
    print("=" * 100)
    print(f"[{r.level.label}] {r.item.name}  ({r.width}x{r.height})  → {r.verdict}")
    for res in r.results:
        for f in sorted(res.findings, key=lambda f: -f.level):
            if f.level >= Level.INFO:
                print(f"   - [{f.level.label}] {res.title}: {f.message}")
    panels = [("원본", Image.open(io.BytesIO(r.item.data)))]
    panels += [(res.title, res.visual) for res in r.results
               if res.visual is not None and (not only_flagged or res.level >= Level.WARN)]
    fig, axes = plt.subplots(1, len(panels), figsize=(6 * len(panels), 5))
    for ax, (title, img) in zip(np.atleast_1d(axes), panels):
        ax.imshow(img.convert("RGB"))
        ax.set_title(title, fontsize=10)
        ax.axis("off")
    plt.tight_layout()
    plt.show()


def inspect(keyword):
    """파일 이름 일부로 사진 하나를 골라 모든 검사 그림을 봅니다. 예: inspect("IMG_0012")"""
    for r in reports:
        if keyword.lower() in r.item.name.lower():
            show_report(r, only_flagged=False)


min_level = LEVEL_BY_LABEL[SHOW_LEVEL]
flagged = sorted((r for r in reports if r.level >= min_level and not r.error), key=lambda r: -r.level)
print(f"'{SHOW_LEVEL}' 이상: {len(flagged)}장\n")
for r in flagged:
    show_report(r)
''')

md("특정 사진을 모든 검사 그림과 함께 보려면 아래처럼 파일 이름 일부를 넣어 실행하세요.")
code('# inspect("IMG_0012")')

md("## 7. 리포트 저장\nHTML 리포트(브라우저로 열기)와 CSV 결과표(엑셀로 열기)를 `D:\\data`에 저장합니다.")
code(r'''
order = sorted(reports, key=lambda r: -r.level)
write_html(order, [str(DATA_DIR)], REPORT_PATH)
df.to_csv(CSV_PATH, index=False, encoding="utf-8-sig")   # 엑셀에서 한글 안 깨지게
print("HTML 리포트:", REPORT_PATH)
print("CSV 결과표:", CSV_PATH)
''')

nb = {"cells": cells, "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
      "language_info": {"name": "python"}}, "nbformat": 4, "nbformat_minor": 5}
for i, c in enumerate(nb["cells"]):
    c["id"] = f"cell-{i:02d}"
    c["source"] = [l for l in c["source"].splitlines(keepends=True)]
OUT.write_text(json.dumps(nb, ensure_ascii=False, indent=1), encoding="utf-8")
print("written", OUT, len(cells), "cells")
