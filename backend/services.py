"""분석 → ATM 세션 생성으로 이어지는 도메인 로직.

라우터는 HTTP 처리만 하고, 실제 판정/세션 생성은 여기에 모은다
(coding-standards.md: 한 함수는 한 가지 일만 한다).
"""
from uuid import uuid4

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


def format_session_id(row_id: int) -> str:
    """세션 행의 id를 QR에 넣을 번호로 만든다 (예: 3 → VP-000003)."""
    return f"{SESSION_ID_PREFIX}{row_id:0{SESSION_ID_DIGITS}d}"


def _pending_session_id() -> str:
    """번호를 배정받기 전 잠깐 채워 두는 임시값.

    session_id는 NOT NULL이라 INSERT 시점에 뭔가는 들어가야 하는데, 이 시점에는
    아직 행 id를 모른다. 두 요청이 동시에 들어와도 서로 부딪히지 않도록
    임시값도 매번 다른 값을 쓴다. 같은 트랜잭션 안에서만 존재하고 커밋 전에
    진짜 번호로 바뀐다.
    """
    return f"pending-{uuid4().hex}"


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

    # 번호는 DB가 배정한 행 id에서 그대로 끌어온다.
    # 직접 세어서(개수든 최댓값이든) 매기면 두 가지가 깨진다 —
    #   (1) 세션을 지우면 이미 쓴 번호가 다시 나온다
    #   (2) 두 요청이 동시에 들어오면 같은 번호를 집는다
    # 둘 다 session_id UNIQUE 제약에 걸려 분석 요청이 500으로 실패한다.
    # id는 DB가 원자적으로 배정하므로 어느 쪽도 일어나지 않는다.
    session = AtmSession(
        session_id=_pending_session_id(),
        analysis_id=analysis.id,
        atm_status=action_to_atm_status(action),
    )
    db.add(session)
    db.flush()  # 여기서 session.id가 정해진다
    session.session_id = format_session_id(session.id)
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
