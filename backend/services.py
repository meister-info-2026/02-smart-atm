"""분석 → ATM 세션 생성으로 이어지는 도메인 로직.

라우터는 HTTP 처리만 하고, 실제 판정/세션 생성은 여기에 모은다
(coding-standards.md: 한 함수는 한 가지 일만 한다).
"""
from sqlalchemy import func
from sqlalchemy.orm import Session

from analysis.rules import analyze_message, risk_level_to_action
from config import SESSION_ID_DIGITS, SESSION_ID_PREFIX
from db.models import AnalysisResult, AtmSession, ControlLog, utcnow

# ATM 상태값 (PRD 5.4)
ATM_READY = "READY"
ATM_WITHDRAW_ENABLED = "WITHDRAW_ENABLED"
ATM_WITHDRAW_BLOCKED = "WITHDRAW_BLOCKED"
ATM_CALL_CENTER = "CALL_CENTER"

# 콜센터 확인 결과 (PRD 8.3)
RESOLUTION_MAINTAINED = "MAINTAINED"
RESOLUTION_RELEASED = "RELEASED"

# 액션 → ATM 초기 상태
_ACTION_TO_STATUS: dict[str, str] = {
    "ALLOW": ATM_WITHDRAW_ENABLED,
    "VERIFY": ATM_WITHDRAW_BLOCKED,  # CAUTION은 추가 확인 전까지 출금을 열지 않는다
    "BLOCK": ATM_WITHDRAW_BLOCKED,
}


def next_session_id(db: Session) -> str:
    """다음 ATM 세션 ID를 만든다 (예: VP-000003)."""
    count = db.query(func.count(AtmSession.id)).scalar() or 0
    return f"{SESSION_ID_PREFIX}{count + 1:0{SESSION_ID_DIGITS}d}"


def action_to_atm_status(action: str) -> str:
    """ATM 동작(ALLOW/VERIFY/BLOCK)에 대응하는 초기 ATM 상태."""
    return _ACTION_TO_STATUS.get(action, ATM_WITHDRAW_BLOCKED)


def run_analysis(
    db: Session,
    *,
    user_id: int,
    message_text: str,
    chat_room_id: int | None = None,
    message_id: int | None = None,
) -> tuple[AnalysisResult, AtmSession]:
    """문자를 분석하고 결과 + ATM 세션을 한 번에 저장한다.

    ATM 세션은 위험 등급과 무관하게 항상 만든다 — SAFE도 ATM에서 '제한 없음'을
    확인할 수 있어야 하고(PRD 9.1), 서버 검증(OF-03)이 필수이기 때문이다.
    """
    result = analyze_message(message_text)
    action = risk_level_to_action(result.risk_level)

    analysis = AnalysisResult(
        user_id=user_id,
        chat_room_id=chat_room_id,
        message_id=message_id,
        message_text=message_text,
        risk_level=result.risk_level,
        risk_score=result.risk_score,
        reasons=result.reasons,
        summary=result.summary,
        engine="rule",
    )
    db.add(analysis)
    db.flush()  # analysis.id 확보

    session = AtmSession(
        session_id=next_session_id(db),
        analysis_id=analysis.id,
        atm_status=action_to_atm_status(action),
    )
    db.add(session)
    db.commit()
    db.refresh(analysis)
    db.refresh(session)
    return analysis, session


def log_control(
    db: Session,
    *,
    device_id: str,
    action: str,
    value: str | None = None,
    actor: str = "device",
) -> None:
    """장치 제어 이력을 남긴다 (db-rules.md control_log)."""
    db.add(ControlLog(device_id=device_id, action=action, value=value, actor=actor))
    db.commit()


def resolve_callcenter(
    db: Session,
    session: AtmSession,
    *,
    resolution: str,
    note: str | None = None,
) -> AtmSession:
    """콜센터 확인 결과를 반영한다.

    db-rules.md '경보성 디바이스 원칙': 제한 상태는 시스템이 스스로 풀지 않는다.
    사람이 RELEASED를 명시적으로 기록해야만 출금이 다시 열린다.
    """
    session.callcenter_resolution = resolution
    session.callcenter_note = note
    session.resolved_at = utcnow()
    session.atm_status = (
        ATM_WITHDRAW_ENABLED if resolution == RESOLUTION_RELEASED else ATM_WITHDRAW_BLOCKED
    )
    db.commit()
    db.refresh(session)
    return session
