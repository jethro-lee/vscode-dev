"""사용법: python -m imgcheck 문서.pdf [사진.jpg ...] -o report.html"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .analyze import analyze_image
from .extract import extract_images
from .models import Level
from .report import write_html, write_json


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="imgcheck",
        description="문서(PDF/DOCX/PPTX)나 이미지의 조작·AI 생성 의심 신호를 분석해 HTML 리포트를 만듭니다.")
    p.add_argument("inputs", nargs="+", help="분석할 파일 (PDF, DOCX, PPTX, XLSX, JPG, PNG 등)")
    p.add_argument("-o", "--output", default="report.html", help="HTML 리포트 경로 (기본: report.html)")
    p.add_argument("--json", help="결과를 JSON으로도 저장할 경로")
    p.add_argument("--save-images", help="문서에서 추출한 원본 이미지를 저장할 폴더")
    args = p.parse_args(argv)

    items = []
    for src in args.inputs:
        try:
            found = extract_images(src)
        except Exception as e:
            print(f"[오류] {src}: {e}", file=sys.stderr)
            continue
        print(f"{Path(src).name}: 이미지 {len(found)}개")
        items.extend(found)

    if not items:
        print("분석할 이미지가 없습니다.", file=sys.stderr)
        return 1

    if args.save_images:
        out_dir = Path(args.save_images)
        out_dir.mkdir(parents=True, exist_ok=True)
        for it in items:
            (out_dir / it.name).write_bytes(it.data)

    reports = []
    for n, it in enumerate(items, start=1):
        rep = analyze_image(it)
        reports.append(rep)
        print(f"  [{n}/{len(items)}] {it.name}: {rep.verdict}")

    write_html(reports, args.inputs, args.output)
    print(f"\nHTML 리포트: {args.output}")
    if args.json:
        write_json(reports, args.json)
        print(f"JSON 결과: {args.json}")

    # 종료 코드: 0=특이사항 없음, 2=주의, 3=의심 (자동화 파이프라인용)
    worst = max(r.level for r in reports)
    return int(worst) if worst >= Level.WARN else 0


if __name__ == "__main__":
    sys.exit(main())
