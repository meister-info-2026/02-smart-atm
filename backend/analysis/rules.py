"""규칙 기반 보이스피싱 위험 판별 엔진 (PRD 5.2).

키워드별 가중치를 범주 단위로 합산하고 최대 100점으로 제한한 뒤,
0~29 SAFE / 30~69 CAUTION / 70~100 DANGER로 등급을 매긴다.
"""
from dataclasses import dataclass, field

from config import RISK_CAUTION_MAX, RISK_SAFE_MAX, RISK_SCORE_MAX

from .keywords import RISK_CATEGORIES

RISK_SAFE = "SAFE"
RISK_CAUTION = "CAUTION"
RISK_DANGER = "DANGER"

# ATM이 취해야 할 동작 (PRD 5.8 / 9.3)
ACTION_ALLOW = "ALLOW"
ACTION_VERIFY = "VERIFY"
ACTION_BLOCK = "BLOCK"

RISK_LEVEL_TO_ACTION: dict[str, str] = {
    RISK_SAFE: ACTION_ALLOW,
    RISK_CAUTION: ACTION_VERIFY,
    RISK_DANGER: ACTION_BLOCK,
}

SUMMARY_MAX_REASONS = 2
SAFE_SUMMARY = "위험 표현이 발견되지 않았습니다"


@dataclass
class AnalysisResult:
    """분석 결과 한 건."""

    risk_level: str
    risk_score: int
    reasons: list[str] = field(default_factory=list)
    matched_keywords: list[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        """탐지 결과 한 줄 요약 (PRD 6.3 summary 필드)."""
        if not self.reasons:
            return SAFE_SUMMARY
        head = [reason.replace(" 감지", "") for reason in self.reasons[:SUMMARY_MAX_REASONS]]
        return " 및 ".join(head) + " 감지"


def score_to_risk_level(score: int) -> str:
    """점수를 위험 등급으로 변환한다 (PRD 5.2 경계값)."""
    if score <= RISK_SAFE_MAX:
        return RISK_SAFE
    if score <= RISK_CAUTION_MAX:
        return RISK_CAUTION
    return RISK_DANGER


def risk_level_to_action(risk_level: str) -> str:
    """위험 등급을 ATM 동작으로 변환한다. 알 수 없는 등급은 안전하게 BLOCK."""
    return RISK_LEVEL_TO_ACTION.get(risk_level, ACTION_BLOCK)


def analyze_message(message: str) -> AnalysisResult:
    """문자 한 건을 규칙 기반으로 분석한다."""
    text = (message or "").strip()
    if not text:
        return AnalysisResult(risk_level=RISK_SAFE, risk_score=0)

    normalized = text.lower()
    score = 0
    reasons: list[str] = []
    matched: list[str] = []

    for category in RISK_CATEGORIES:
        hits = [kw for kw in category.keywords if kw.lower() in normalized]
        if not hits:
            continue
        # 범주당 가중치는 한 번만 더한다 (같은 범주 키워드 중복 가산 방지)
        score += category.weight
        reasons.append(category.reason)
        matched.extend(hits)

    score = min(score, RISK_SCORE_MAX)
    return AnalysisResult(
        risk_level=score_to_risk_level(score),
        risk_score=score,
        reasons=reasons,
        matched_keywords=matched,
    )
