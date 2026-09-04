"""콜센터 라우터 — 사용자향 (상담원 로그인 JWT 필요).

PRD 8: AI와 ATM의 자동 판단 이후 사람이 최종 상황을 확인하는 단계다.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from api_responses import api_error, ok
from db.database import get_db
from db.models import AnalysisResult, AtmSession, User
from schemas.models import CallcenterResolveRequest, CallcenterSessionResponse
from security.jwt_auth import require_callcenter_agent
from services import ATM_CALL_CENTER, ATM_WITHDRAW_BLOCKED, resolve_callcenter
from websocket_manager import ws_manager

router = APIRouter(prefix="/api/v1/callcenter", tags=["callcenter"])

SESSION_LIST_LIMIT = 50
ATTENTION_STATUSES = (ATM_WITHDRAW_BLOCKED, ATM_CALL_CENTER)


def _to_response(session: AtmSession, analysis: AnalysisResult, user: User) -> dict:
    """상담원이 확인해야 할 정보 (PRD 8.2)."""
    return CallcenterSessionResponse(
        session_id=session.session_id,
        analysis_id=analysis.id,
        user_display_name=user.display_name,
        risk_level=analysis.risk_level,
        risk_score=analysis.risk_score,
        reasons=list(analysis.reasons or []),
        message_text=analysis.message_text,
        atm_status=session.atm_status,
        callcenter_resolution=session.callcenter_resolution,
        detected_at=analysis.detected_at,
        scanned_at=session.scanned_at,
        resolved_at=session.resolved_at,
    ).model_dump()


def _load(db: Session, session_id: str) -> tuple[AtmSession, AnalysisResult, User]:
    session = db.query(AtmSession).filter(AtmSession.session_id == session_id).first()
    if session is None:
        raise api_error(404, "SESSION_NOT_FOUND", "세션을 찾을 수 없습니다.")
    analysis = db.get(AnalysisResult, session.analysis_id)
    user = db.get(User, analysis.user_id) if analysis else None
    if analysis is None or user is None:
        raise api_error(404, "SESSION_INCOMPLETE", "세션에 연결된 정보가 없습니다.")
    return session, analysis, user


@router.get("/sessions")
def list_sessions(
    only_open: bool = Query(default=True, description="확인이 필요한 세션만 볼지 여부"),
    _agent: User = Depends(require_callcenter_agent),
    db: Session = Depends(get_db),
) -> dict:
    """상담원이 확인해야 할 세션 목록을 최신순으로 돌려준다."""
    query = (
        db.query(AtmSession, AnalysisResult, User)
        .join(AnalysisResult, AtmSession.analysis_id == AnalysisResult.id)
        .join(User, AnalysisResult.user_id == User.id)
    )
    if only_open:
        query = query.filter(
            AtmSession.atm_status.in_(ATTENTION_STATUSES),
            AtmSession.callcenter_resolution.is_(None),
        )
    rows = query.order_by(AtmSession.id.desc()).limit(SESSION_LIST_LIMIT).all()
    return ok([_to_response(s, a, u) for s, a, u in rows])


@router.get("/sessions/{session_id}")
def read_session(
    session_id: str,
    _agent: User = Depends(require_callcenter_agent),
    db: Session = Depends(get_db),
) -> dict:
    """세션 한 건의 상세 확인 정보를 돌려준다."""
    session, analysis, user = _load(db, session_id)
    return ok(_to_response(session, analysis, user))


@router.post("/resolve/{session_id}")
async def resolve_session(
    session_id: str,
    payload: CallcenterResolveRequest,
    _agent: User = Depends(require_callcenter_agent),
    db: Session = Depends(get_db),
) -> dict:
    """상담원 확인 결과를 기록한다 — RELEASED(제한 해제) 또는 MAINTAINED(제한 유지)."""
    session, analysis, user = _load(db, session_id)
    session = resolve_callcenter(db, session, resolution=payload.resolution, note=payload.note)

    await ws_manager.broadcast(
        {
            "type": "callcenter_resolved",
            "session_id": session.session_id,
            "callcenter_resolution": session.callcenter_resolution,
            "atm_status": session.atm_status,
        }
    )
    return ok(_to_response(session, analysis, user))
