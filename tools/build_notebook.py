"""imgcheck 소스를 셀 하나에 모두 넣은 단독 실행 노트북을 만든다.

사용법: python tools/build_notebook.py . notebooks/imgcheck_folder.ipynb
"""

import json
import sys
from pathlib import Path

ROOT = Path(sys.argv[1])
OUT = Path(sys.argv[2])

MODULES = [
    "models.py", "checks/_util.py", "extract.py",
    "checks/metadata.py", "checks/c2pa_check.py", "checks/ela.py",
    "checks/noise.py", "checks/copymove.py", "checks/ai_api.py",
    "analyze.py", "report.py",
]


def module_src(rel: str) -> str:
    s = (ROOT / "imgcheck" / rel).read_text(encoding="utf-8")
    keep = [l for l in s.splitlines()
            if not l.startswith("from .") and l != "from __future__ import annotations"]
    return f"# ---------- {rel} ----------\n" + "\n".join(keep).strip() + "\n"


HEADER = r'''
# =====================================================================
#  폴더 안의 사진/문서 이미지 조작·AI 생성 의심 신호 일괄 검사
#  사용법: 아래 [설정]의 DATA_DIR만 확인하고 이 셀을 실행하세요 (Shift+Enter).
# =====================================================================
from __future__ import annotations

# ---------------------------- [설정] ----------------------------------
DATA_DIR = r"D:\data"     # 검사할 폴더
RECURSIVE = True           # 하위 폴더까지 검사
SHOW_IMAGES = True         # 의심/주의 사진을 그림으로 보여줄지
MAX_SHOW = 30              # 그림으로 보여줄 최대 장수
SIGHTENGINE_API_USER = ""  # (선택) AI 판별 API 키. 비워두면 사진이 외부로 전송되지 않음
SIGHTENGINE_API_SECRET = ""
# ----------------------------------------------------------------------

import importlib.util, subprocess, sys
_NEED = {"PIL": "pillow", "numpy": "numpy", "cv2": "opencv-python-headless", "pymupdf": "pymupdf",
         "c2pa": "c2pa-python", "pandas": "pandas", "matplotlib": "matplotlib"}
_missing = [pkg for mod, pkg in _NEED.items() if importlib.util.find_spec(mod) is None]
if _missing:
    print("필요한 패키지 설치 중:", ", ".join(_missing))
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", *_missing])
    importlib.invalidate_caches()

import os
if SIGHTENGINE_API_USER and SIGHTENGINE_API_SECRET:
    os.environ["SIGHTENGINE_API_USER"] = SIGHTENGINE_API_USER
    os.environ["SIGHTENGINE_API_SECRET"] = SIGHTENGINE_API_SECRET

__version__ = "0.1.0"
'''

RUN = r'''
# ============================== 실행 ==================================
import io, platform, time
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from IPython.display import display

ALL_CHECKS = [check_metadata, check_c2pa, check_ela, check_noise, check_copymove, check_ai_api]
SHORT = {"metadata": "메타데이터", "c2pa": "C2PA", "ela": "ELA", "noise": "노이즈",
         "copymove": "복제", "ai_api": "AI판별"}

data_dir = Path(DATA_DIR)
assert data_dir.exists(), f"폴더가 없습니다: {data_dir}"
report_path = data_dir / "imgcheck_report.html"
csv_path = data_dir / "imgcheck_result.csv"
own_outputs = {report_path.name, csv_path.name}

files = sorted(p for p in (data_dir.rglob("*") if RECURSIVE else data_dir.glob("*"))
               if p.is_file() and p.name not in own_outputs and not p.name.startswith("~$"))
print(f"폴더: {data_dir}\n파일 {len(files)}개 검사 시작\n")

reports, rows = [], []
t0 = time.time()
for f in files:
    rel = str(f.relative_to(data_dir))
    try:
        found = extract_images(f)
    except ValueError:
        rows.append({"판정": "검사 불가", "파일": rel, "크기": "", "주요 신호": "지원하지 않는 형식", "_lv": -1})
        continue
    except Exception as e:
        rows.append({"판정": "검사 불가", "파일": rel, "크기": "", "주요 신호": f"파일 열기 실패: {e}", "_lv": -1})
        continue
    if not found:
        rows.append({"판정": "검사 불가", "파일": rel, "크기": "", "주요 신호": "문서 안에 검사할 이미지 없음", "_lv": -1})
        continue
    for it in found:
        it.name = rel if f.suffix.lower() in IMAGE_EXTS else f"{rel} :: {it.name}"
        rep = analyze_image(it)
        reports.append(rep)
        row = {"판정": rep.level.label, "파일": it.name, "크기": f"{rep.width}x{rep.height}"}
        for res in rep.results:
            row[SHORT.get(res.name, res.name)] = "건너뜀" if res.skipped else res.level.label
        row["주요 신호"] = " / ".join(fd.message for res in rep.results for fd in res.findings
                                    if fd.level >= Level.WARN) or rep.error or ""
        row["_lv"] = int(rep.level)
        rows.append(row)
        print(f"  {rep.level.label:>2} | {it.name}")

print(f"\n완료: 이미지 {len(reports)}개, {time.time() - t0:.1f}초")

# ---- 요약표 ----
cols = ["판정", "파일", "크기", *SHORT.values(), "주요 신호"]
df = (pd.DataFrame(rows).sort_values(["_lv", "파일"], ascending=[False, True])
      .drop(columns="_lv").reindex(columns=cols).fillna("").reset_index(drop=True))
print("\n[판정별 개수]")
print(df["판정"].value_counts().to_string())
pd.set_option("display.max_colwidth", 120)
display(df)

# ---- 의심/주의 사진 그림 ----
if SHOW_IMAGES:
    if platform.system() == "Windows":
        plt.rcParams["font.family"] = "Malgun Gothic"
    elif platform.system() == "Darwin":
        plt.rcParams["font.family"] = "AppleGothic"
    plt.rcParams["axes.unicode_minus"] = False
    flagged = sorted((r for r in reports if r.level >= Level.WARN and not r.error), key=lambda r: -r.level)
    for r in flagged[:MAX_SHOW]:
        print("=" * 100)
        print(f"[{r.level.label}] {r.item.name} ({r.width}x{r.height}) → {r.verdict}")
        for res in r.results:
            for fd in sorted(res.findings, key=lambda x: -x.level):
                if fd.level >= Level.WARN:
                    print(f"   - [{fd.level.label}] {res.title}: {fd.message}")
        panels = [("원본", Image.open(io.BytesIO(r.item.data)))]
        panels += [(res.title, res.visual) for res in r.results
                   if res.visual is not None and res.level >= Level.WARN]
        fig, axes = plt.subplots(1, len(panels), figsize=(6 * len(panels), 5))
        for ax, (title, img) in zip(np.atleast_1d(axes), panels):
            ax.imshow(img.convert("RGB"))
            ax.set_title(title, fontsize=10)
            ax.axis("off")
        plt.tight_layout()
        plt.show()
    if len(flagged) > MAX_SHOW:
        print(f"... 외 {len(flagged) - MAX_SHOW}장은 HTML 리포트에서 확인하세요.")

# ---- 저장 ----
write_html(sorted(reports, key=lambda r: -r.level), [str(data_dir)], report_path)
df.to_csv(csv_path, index=False, encoding="utf-8-sig")  # 엑셀에서 한글 안 깨지게
print(f"\nHTML 리포트: {report_path}\nCSV 결과표: {csv_path}")
'''

INTRO = r"""
# 사진 조작·AI 생성 의심 신호 일괄 검사

아래 **셀 하나만 실행**하면 `D:\data` 폴더(하위 폴더 포함)의 모든 파일을 검사합니다.

- 대상: 사진(JPG·PNG·WEBP·TIFF·HEIC 등) + PDF·Word·PowerPoint·Excel·HWPX 안의 이미지
- 결과: 요약표, 의심 사진의 표시 그림, `imgcheck_report.html`(브라우저용), `imgcheck_result.csv`(엑셀용)
- 필요한 패키지가 없으면 처음 실행할 때 자동으로 설치합니다.

> ⚠️ 진위를 확정하지 않습니다. `의심`/`주의`는 표시된 영역을 사람이 직접 확인하라는 뜻이고, `정상`은 "이 검사로는 흔적을 못 찾았다"는 뜻입니다.
"""

code = HEADER.strip() + "\n\n" + "\n\n".join(module_src(m) for m in MODULES) + "\n" + RUN.strip() + "\n"
compile(code.replace("%", "#"), "notebook_cell", "exec")  # 문법 확인

cells = [
    {"cell_type": "markdown", "id": "intro", "metadata": {}, "source": INTRO.strip()},
    {"cell_type": "code", "id": "run-all", "metadata": {}, "execution_count": None, "outputs": [], "source": code},
]
for c in cells:
    c["source"] = c["source"].splitlines(keepends=True)
nb = {"cells": cells, "nbformat": 4, "nbformat_minor": 5,
      "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                   "language_info": {"name": "python"}}}
OUT.write_text(json.dumps(nb, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"written {OUT} ({len(code.splitlines())} lines in one cell)")
