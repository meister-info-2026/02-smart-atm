"""보이스피싱 위험 키워드 사전 (PRD 5.2 '분석 대상' 7개 범주).

규칙 기반 1차 구현이다. 외부 AI API를 붙인 뒤에도 이 사전은 백업 판별 수단으로
그대로 유지한다 (PRD 11.3 네트워크 의존성 / 14.3 위험 요소 대응).

가중치는 "범주 단위"로 한 번만 더한다 — 같은 범주의 키워드가 여러 개 걸려도
중복 가산하지 않는다.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class RiskCategory:
    """위험 범주 하나의 정의."""

    code: str
    reason: str  # 사용자에게 그대로 보여주는 탐지 근거 문구
    weight: int
    keywords: tuple[str, ...]


# PRD 5.2 분석 대상 7개 범주
RISK_CATEGORIES: tuple[RiskCategory, ...] = (
    RiskCategory(
        code="IMPERSONATION",
        reason="기관 사칭 표현 감지",
        weight=35,
        keywords=(
            "검찰", "검사입니다", "수사관", "경찰청", "경찰서", "금융감독원", "금감원",
            "국세청", "우체국입니다", "법원입니다", "공공기관", "수사기관",
            "은행 직원입니다", "금융기관입니다", "보건복지부", "질병관리청",
        ),
    ),
    RiskCategory(
        code="CRIME_INVOLVEMENT",
        reason="범죄 연루 언급 감지",
        weight=25,
        keywords=(
            "범죄에 연루", "범죄 연루", "사건에 연루", "명의도용", "명의 도용",
            "대포통장", "자금세탁", "자금 세탁", "구속", "체포", "수사 중",
            "계좌가 도용", "피의자", "출석 요구", "압수",
        ),
    ),
    RiskCategory(
        code="CASH_WITHDRAWAL",
        reason="현금 인출 요구 감지",
        weight=30,
        keywords=(
            "현금을 인출", "현금 인출", "인출해", "인출하세요", "인출하여",
            "돈을 찾아", "돈을 인출", "출금하세요", "출금해", "현금으로 찾",
            "예금을 찾", "전액 인출",
        ),
    ),
    RiskCategory(
        code="TRANSFER_REQUEST",
        reason="송금·이체 요구 감지",
        weight=25,
        keywords=(
            "송금하세요", "송금해", "송금 바랍니다", "이체하세요", "이체해",
            "계좌로 보내", "안전계좌", "안전 계좌", "입금하세요", "입금해 주세요",
        ),
    ),
    RiskCategory(
        code="URGENCY",
        reason="긴급 행동 요구 감지",
        weight=15,
        keywords=(
            "지금 바로", "즉시", "당장", "오늘 안에", "서둘러", "빨리",
            "시간이 없", "마감", "긴급", "늦으면",
        ),
    ),
    RiskCategory(
        code="SECRECY",
        reason="비밀 유지 요구 감지",
        weight=25,
        keywords=(
            "말하지 마", "말씀하지 마", "알리지 마", "비밀로", "비밀 유지",
            "누구에게도", "가족에게 말", "은행 직원에게 말", "혼자 오",
            "발설하지", "함구",
        ),
    ),
    RiskCategory(
        code="HANDOVER_LOCATION",
        reason="특정 장소 현금 전달 요구 감지",
        weight=25,
        keywords=(
            "지정 장소", "지정된 장소", "장소로 가져", "가지고 오세요", "가져오세요",
            "직접 전달", "만나서 전달", "수거", "직원이 찾아", "수령하러",
        ),
    ),
)
