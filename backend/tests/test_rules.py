"""규칙 기반 분석 엔진 테스트 (PRD 14.2 TC-01~TC-03, 5.2 경계값)."""
import pytest

from analysis.rules import (
    RISK_CAUTION,
    RISK_DANGER,
    RISK_SAFE,
    analyze_message,
    risk_level_to_action,
    score_to_risk_level,
)

NORMAL_MESSAGE = "오늘 오후 3시에 병원 예약이 있습니다."
IMPERSONATION_MESSAGE = (
    "검찰입니다. 계좌가 범죄에 연루되었습니다. 현금 500만 원을 인출해 지정 장소로 가져오세요."
)
SECRECY_MESSAGE = "은행 직원이나 가족에게 말하지 마시고 지금 바로 돈을 찾아오세요."


def test_tc01_normal_message_is_safe() -> None:
    """TC-01: 정상 문자 → SAFE, 출금 제한 없음."""
    result = analyze_message(NORMAL_MESSAGE)
    assert result.risk_level == RISK_SAFE
    assert result.risk_score == 0
    assert result.reasons == []
    assert risk_level_to_action(result.risk_level) == "ALLOW"


def test_tc02_impersonation_with_cash_demand_is_danger() -> None:
    """TC-02: 기관 사칭 + 현금 요구 → DANGER, 근거 표시, 출금 차단."""
    result = analyze_message(IMPERSONATION_MESSAGE)
    assert result.risk_level == RISK_DANGER
    assert result.risk_score == 100  # 가중치 합이 100을 넘어도 100으로 제한된다
    assert "기관 사칭 표현 감지" in result.reasons
    assert "현금 인출 요구 감지" in result.reasons
    assert "특정 장소 현금 전달 요구 감지" in result.reasons
    assert risk_level_to_action(result.risk_level) == "BLOCK"


def test_tc03_secrecy_request_is_detected() -> None:
    """TC-03: 비밀 유지 요구 → 위험 또는 의심, 비밀 유지 요구 탐지."""
    result = analyze_message(SECRECY_MESSAGE)
    assert result.risk_level in (RISK_CAUTION, RISK_DANGER)
    assert "비밀 유지 요구 감지" in result.reasons


def test_empty_message_is_safe() -> None:
    """빈 문자열은 위험 0점으로 처리한다."""
    assert analyze_message("").risk_score == 0
    assert analyze_message("   ").risk_level == RISK_SAFE


def test_same_category_keywords_are_not_double_counted() -> None:
    """같은 범주 키워드가 여러 개 걸려도 가중치는 한 번만 더한다."""
    once = analyze_message("지금 바로")
    twice = analyze_message("지금 바로 당장 즉시 서둘러")
    assert once.risk_score == twice.risk_score


@pytest.mark.parametrize(
    ("score", "expected"),
    [(0, RISK_SAFE), (29, RISK_SAFE), (30, RISK_CAUTION), (69, RISK_CAUTION),
     (70, RISK_DANGER), (100, RISK_DANGER)],
)
def test_risk_level_boundaries(score: int, expected: str) -> None:
    """PRD 5.2 경계값: 0~29 SAFE / 30~69 CAUTION / 70~100 DANGER."""
    assert score_to_risk_level(score) == expected


def test_caution_maps_to_verify() -> None:
    """PRD 9.3: CAUTION은 허용도 차단도 아닌 VERIFY(추가 확인)다."""
    assert risk_level_to_action(RISK_CAUTION) == "VERIFY"


def test_summary_is_generated_for_danger() -> None:
    """summary는 상위 근거 2개를 합친 한 줄 요약이다 (PRD 6.3)."""
    result = analyze_message(IMPERSONATION_MESSAGE)
    assert result.summary.endswith("감지")
    assert "기관 사칭" in result.summary
