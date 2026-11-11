from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum

from PIL import Image


class Level(IntEnum):
    """신호 수준. 숫자가 클수록 의심스럽다."""

    OK = 0      # 특이사항 없음
    INFO = 1    # 참고 정보
    WARN = 2    # 주의
    ALERT = 3   # 강한 의심 신호

    @property
    def label(self) -> str:
        return {0: "정상", 1: "참고", 2: "주의", 3: "의심"}[self.value]


@dataclass
class Finding:
    level: Level
    message: str


@dataclass
class CheckResult:
    name: str
    title: str
    findings: list[Finding] = field(default_factory=list)
    visual: Image.Image | None = None   # 리포트에 넣을 시각화 이미지
    data: dict = field(default_factory=dict)
    skipped: str | None = None          # 건너뛴 이유

    @property
    def level(self) -> Level:
        if not self.findings:
            return Level.OK
        return max(f.level for f in self.findings)

    def add(self, level: Level, message: str) -> None:
        self.findings.append(Finding(level, message))


@dataclass
class ImageItem:
    """분석 대상 이미지 하나."""

    name: str            # 표시용 이름 (예: page3_img1.jpeg)
    source: str          # 원본 파일 경로
    data: bytes          # 원본 바이트 (재인코딩하지 않은 그대로)
    ext: str             # jpeg, png ...
    location: str = ""   # 문서 내 위치 (예: "3페이지")


@dataclass
class ImageReport:
    item: ImageItem
    width: int = 0
    height: int = 0
    results: list[CheckResult] = field(default_factory=list)
    error: str | None = None

    @property
    def level(self) -> Level:
        if not self.results:
            return Level.OK
        return max(r.level for r in self.results)

    @property
    def verdict(self) -> str:
        return {
            Level.OK: "특이사항 없음",
            Level.INFO: "특이사항 없음 (참고 정보 있음)",
            Level.WARN: "주의 - 사람이 확인 필요",
            Level.ALERT: "조작/AI 생성 의심 신호 있음",
        }[self.level]
