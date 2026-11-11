# imgcheck — 문서 이미지 진위 분석 도구

PDF·Word·PowerPoint 문서나 이미지 파일을 넣으면, 들어 있는 이미지마다
**조작 또는 AI 생성이 의심되는 신호**를 찾아 HTML 리포트로 보여줍니다.

> ⚠️ 이 도구는 진위를 **확정하지 않습니다.** 의심 신호를 찾아 사람이 판단할 근거를 주는 도구입니다.
> "특이사항 없음"은 "이 검사들로는 흔적을 찾지 못했다"는 뜻이며 진본 보증이 아닙니다.
> 법적 분쟁 등 중요한 사안은 전문 디지털 포렌식 감정을 권합니다.

## 설치

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Python 3.10 이상이 필요합니다.

## 사용법

```bash
# 문서 하나 검사 → report.html 생성
python check.py 고객문서.pdf

# 여러 파일, 리포트 경로·JSON 결과·추출 이미지 저장
python check.py 계약서.docx 현장사진.jpg -o 결과.html --json 결과.json --save-images extracted/
```

- 지원 입력: `PDF`, `DOCX`, `PPTX`, `XLSX`, `HWPX`, `JPG`, `PNG`, `WEBP`, `TIFF` 등
- 문서 안의 이미지는 **재압축 없이 원본 바이트 그대로** 꺼내서 분석합니다.
- 종료 코드: `0` 특이사항 없음, `2` 주의, `3` 의심 (자동화에 활용 가능)

## Jupyter 노트북으로 폴더 통째로 검사

`notebooks/imgcheck_folder.ipynb` 는 설치나 다른 파일 없이 **노트북 하나만으로** 동작합니다.

1. 노트북을 Jupyter에서 열고, 2번 셀의 `DATA_DIR = Path(r"D:\data")` 를 검사할 폴더로 지정
2. `Run All` 실행 → 요약표, 의심 사진의 표시 그림, `imgcheck_report.html`·`imgcheck_result.csv` 가 생성됨
3. 특정 사진만 자세히 보려면 `inspect("파일명 일부")`

노트북은 `python tools/build_notebook.py . notebooks/imgcheck_folder.ipynb` 로 `imgcheck/` 소스에서 다시 만들 수 있습니다.

## 검사 항목

| 검사 | 찾는 것 | 비고 |
|---|---|---|
| 메타데이터 (EXIF/XMP/PNG) | AI 생성기 이름(Midjourney, DALL·E, Firefly, SDXL 등), 프롬프트 정보, Photoshop 같은 편집 프로그램, 카메라 정보 | 메타데이터는 쉽게 지워지므로 없다고 조작은 아님 |
| C2PA 출처 정보 | 콘텐츠 자격증명에 기록된 AI 생성 여부, 편집 이력, 서명 검증 결과 | OpenAI·Adobe·Google 등이 넣는 표준 |
| ELA 압축 오류 분석 | 나중에 붙여 넣거나 고친 영역 (압축 이력이 주변과 다른 곳) | JPEG에서 가장 잘 동작 |
| 노이즈 일관성 | 합성된 영역, 지우기·뭉개기·AI 덧칠 영역 | 초점 흐림·복잡한 무늬에서 오탐 가능 |
| 복제-이동 탐지 | 같은 이미지 안에서 복사·붙여넣기한 부분 | 타일·창문 등 반복 무늬에서 오탐 가능 |
| AI 생성 판별 API (선택) | 외부 판별 모델의 AI 생성 확률 | API 키가 있을 때만 동작 |

각 결과는 `정상 / 참고 / 주의 / 의심` 4단계로 표시되고, ELA·노이즈·복제 검사는
어느 부분이 의심되는지 원본 위에 표시한 이미지를 함께 보여줍니다.

## AI 판별 API 연동 (선택)

위 기본 검사만으로는 **메타데이터가 지워진 AI 생성 이미지**를 잡기 어렵습니다.
이런 경우 [Sightengine](https://sightengine.com)의 AI 생성 판별 모델을 연동할 수 있습니다.

```bash
export SIGHTENGINE_API_USER=발급받은_user
export SIGHTENGINE_API_SECRET=발급받은_secret
python check.py 고객문서.pdf
```

- 키를 설정하지 않으면 이 검사는 건너뛰고, **이미지는 외부로 전송되지 않습니다.**
- 키를 설정하면 이미지가 Sightengine 서버로 전송되므로, 고객 문서라면 사전에 동의를 받으세요.
- 결과는 확률이며 오탐·미탐이 있습니다.

## 결과 해석 가이드

- **의심**: 메타데이터/C2PA에 AI 생성 기록이 있거나, 복제 영역이 뚜렷한 경우. 근거가 비교적 강합니다.
- **주의**: 통계적으로 튀는 영역이 있음. 리포트의 표시 영역을 눈으로 확인하세요. 정상 사진에서도 나올 수 있습니다.
- **참고**: 카메라 정보 없음, PNG라 ELA 신뢰도 낮음 등 판단에 참고할 정보.
- 문서에 들어간 이미지는 편집기가 재압축하거나 메타데이터를 지우는 일이 많으므로,
  가능하면 **원본 사진 파일을 받아 다시 검사**하는 것이 가장 정확합니다.
- 역이미지 검색(Google 렌즈, TinEye)으로 원본 출처를 찾는 것도 함께 하면 좋습니다.

## 고객 응대 문구 예시

> 제출하신 문서의 이미지 N장에 대해 메타데이터, 콘텐츠 출처 정보(C2PA), 압축 오류 분석,
> 노이즈 분석, 복제 영역 탐지를 수행했으며, 조작이나 AI 생성을 의심할 만한 흔적은 발견되지 않았습니다.
> 다만 이는 위 검사 범위 내의 결과이며 진본 여부를 보증하는 것은 아닙니다.

## 개발

```bash
pip install pytest
python -m pytest tests
```

구조:

```
imgcheck/
  extract.py        # PDF/Office/이미지에서 원본 이미지 추출
  analyze.py        # 검사 실행
  report.py         # HTML/JSON 리포트
  checks/           # 개별 검사 (metadata, c2pa_check, ela, noise, copymove, ai_api)
check.py            # 간편 실행 스크립트
```
