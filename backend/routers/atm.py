"""ATM 라우터 — 디바이스향 (X-Device-Api-Key 필요).

api-rules.md '인증 분리': 이 라우터의 엔드포인트는 라즈베리파이 ATM 전용이며
사용자 JWT를 요구하지 않는다. 반대로 사용자향 엔드포인트에 디바이스 키만으로
접근할 수 없다.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from analysis.rules import ACTION_ALLOW, risk_level_to_action
from api_responses import api_error, ok
from db.database import get_db
from db.models import AnalysisResult, AtmSession, utcnow
from schemas.models import AtmScanRequest, AtmSessionStatusResponse, AtmVerifyResponse
from security.device_auth import require_device_key
from services import ATM_WITHDRAW_ENABLED, RESOLUTION_RELEASED, log_control
from websocket_manager import ws_manager

router = APIRouter(
    prefix="/api/v1/atm",
    tags=["atm"],
    dependencies=[Depends(require_device_key)],
)

CASH_DISPENSER_DEVICE_ID = "cash_dispenser_1"
QR_SCANNER_DEVICE_ID = "qr_scanner_1"


def _load_session(db: Session, session_id: str) -> tuple[AtmSession, AnalysisResult]:
    """세션을 찾는다. 없으면 404 — 잘못된 QR은 거래 제어에 쓰지 않는다(TC-04)."""
    session = db.query(AtmSession).filter(AtmSession.session_id == session_id).first()
    if session is None:
        raise api_error(404, "SESSION_NOT_FOUND", "등록되지 않은 QR입니다. 거래에 사용할 수 없습니다.")
    analysis = db.get(AnalysisResult, session.analysis_id)
    if analysis is None:
        raise api_error(404, "ANALYSIS_NOT_FOUND", "세션에 연결된 분석 결과가 없습니다.")
    return session, analysis


def _current_action(session: AtmSession, analysis: AnalysisResult) -> str:
    """지금 ATM이 취해야 할 동작 — 서버가 가진 두 가지 사실만으로 정한다.

    (1) 분석 결과의 위험 등급, (2) 사람이 남긴 콜센터 확인 결과.
    콜센터가 제한을 해제(RELEASED)했다면 위험 등급과 무관하게 ALLOW다 —
    사람의 최종 판단이 자동 판정을 뒤집는 유일한 경로다(PRD 8.3).

    ATM이 보고한 `atm_status`는 판단 근거로 쓰지 않는다. 그 값을 믿으면
    디바이스가 스스로 WITHDRAW_ENABLED를 보고하는 것만으로 DANGER 판정이
    풀려, db-rules.md의 경보성 디바이스 원칙이 깨진다.
    """
    if session.callcenter_resolution == RESOLUTION_RELEASED:
        return ACTION_ALLOW
    return risk_level_to_action(analysis.risk_level)


@router.get("/verify/{session_id}")
def verify_session(session_id: str, db: Session = Depends(get_db)) -> dict:
    """QR에서 읽은 session_id로 위험 정보를 서버에서 조회한다 (OF-03, 필수)."""
    session, analysis = _load_session(db, session_id)
    return ok(
        AtmVerifyResponse(
            session_id=session.session_id,
            risk_level=analysis.risk_level,
            risk_score=analysis.risk_score,
            action=_current_action(session, analysis),
            atm_status=session.atm_status,
            detected_at=analysis.detected_at,
            summary=analysis.summary,
            reasons=list(analysis.reasons or []),
        ).model_dump()
    )


@router.post("/scan")
async def report_scan(payload: AtmScanRequest, db: Session = Depends(get_db)) -> dict:
    """ATM이 QR을 인식한 결과와 전환된 상태를 보고한다."""
    session, analysis = _load_session(db, payload.session_id)
    opens_withdrawal = payload.atm_status == ATM_WITHDRAW_ENABLED
    if opens_withdrawal and _current_action(session, analysis) != ACTION_ALLOW:
        # 제한은 시스템이 스스로 풀지 않는다 (db-rules.md 경보성 디바이스 원칙).
        # 콜센터가 RELEASED를 기록하기 전에는 출금 가능 상태로 기록해 주지 않는다.
        raise api_error(
            409,
            "RELEASE_NOT_AUTHORIZED",
            "콜센터 확인 전에는 출금 가능 상태로 바꿀 수 없습니다.",
        )
    session.atm_status = payload.atm_status
    session.scanned_at = utcnow()
    db.commit()
    db.refresh(session)

    log_control(
        db,
        device_id=QR_SCANNER_DEVICE_ID,
        action="qr_scanned",
        value=session.session_id,
        actor="device",
    )
    await ws_manager.broadcast(
        {
            "type": "atm_scan",
            "session_id": session.session_id,
            "risk_level": analysis.risk_level,
            "risk_score": analysis.risk_score,
            "atm_status": session.atm_status,
        }
    )
    return ok(
        AtmSessionStatusResponse(
            session_id=session.session_id,
            atm_status=session.atm_status,
            callcenter_resolution=session.callcenter_resolution,
            action=_current_action(session, analysis),
        ).model_dump()
    )


@router.get("/session-status/{session_id}")
def read_session_status(session_id: str, db: Session = Depends(get_db)) -> dict:
    """ATM이 몇 초마다 폴링해 콜센터 확인 결과를 확인한다."""
    session, analysis = _load_session(db, session_id)
    return ok(
        AtmSessionStatusResponse(
            session_id=session.session_id,
            atm_status=session.atm_status,
            callcenter_resolution=session.callcenter_resolution,
            action=_current_action(session, analysis),
        ).model_dump()
    )


@router.post("/withdraw-attempt/{session_id}")
async def report_withdraw_attempt(
    session_id: str,
    dispensed: bool,
    db: Session = Depends(get_db),
) -> dict:
    """출금 버튼을 눌렀을 때 실제로 배출했는지 보고한다 (FR-08/FR-09 시연 근거).

    배출 여부 판단 자체는 ATM이 로컬에서 하고, 여기서는 기록만 남긴다.
    """
    session, analysis = _load_session(db, session_id)
    log_control(
        db,
        device_id=CASH_DISPENSER_DEVICE_ID,
        action="dispense" if dispensed else "dispense_blocked",
        value=session.session_id,
        actor="device",
    )
    await ws_manager.broadcast(
        {
            "type": "withdraw_attempt",
            "session_id": session.session_id,
            "dispensed": dispensed,
            "atm_status": session.atm_status,
            "risk_level": analysis.risk_level,
        }
    )
    return ok({"session_id": session.session_id, "dispensed": dispensed})
