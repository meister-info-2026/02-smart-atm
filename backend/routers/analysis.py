"""문자 분석 라우터 — 사용자향 (JWT 필요).

PRD 5.8 확정 API:
  POST /api/v1/analysis/chats/{chat_id}   채팅방 메시지 분석
  GET  /api/v1/analysis/{analysis_id}      분석 결과 조회
  GET  /api/v1/analysis/{analysis_id}/atm  ATM 연동 세션 조회 (QR 재료)
추가:
  POST /api/v1/analysis                    직접 입력 문자 분석 (FR-01 '직접 입력: 필수')
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from analysis.rules import risk_level_to_action
from api_responses import api_error, ok
from db.database import get_db
from db.models import AnalysisResult, AtmSession, Message, User
from routers.chats import require_chat_membership
from schemas.models import AnalysisResponse, AnalyzeRequest, AtmSessionResponse
from security.jwt_auth import get_current_user
from services import run_analysis

router = APIRouter(prefix="/api/v1/analysis", tags=["analysis"])


def _to_response(analysis: AnalysisResult, session: AtmSession | None) -> dict:
    return AnalysisResponse(
        analysis_id=analysis.id,
        risk_level=analysis.risk_level,
        risk_score=analysis.risk_score,
        reasons=list(analysis.reasons or []),
        summary=analysis.summary,
        detected_at=analysis.detected_at,
        message_text=analysis.message_text,
        session_id=session.session_id if session else None,
        atm_action=risk_level_to_action(analysis.risk_level),
    ).model_dump()


def _load_owned_analysis(db: Session, analysis_id: int, user_id: int) -> AnalysisResult:
    analysis = db.get(AnalysisResult, analysis_id)
    if analysis is None or analysis.user_id != user_id:
        raise api_error(404, "ANALYSIS_NOT_FOUND", "분석 결과를 찾을 수 없습니다.")
    return analysis


@router.post("")
def analyze_direct_input(
    payload: AnalyzeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """사용자가 직접 입력한 문자를 분석한다."""
    text = (payload.message or "").strip()
    if not text:
        raise api_error(422, "MESSAGE_REQUIRED", "분석할 문자 내용을 입력해 주세요.")
    analysis, session = run_analysis(db, user_id=current_user.id, message_text=text)
    return ok(_to_response(analysis, session))


@router.post("/chats/{chat_id}")
def analyze_chat_message(
    chat_id: int,
    payload: AnalyzeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """채팅방에서 고른 메시지(message_id)를 분석한다.

    message_id가 없으면 채팅방의 가장 최근 메시지를 분석 대상으로 삼는다.

    응답에 문자 원문(message_text)이 실리므로, 목록 조회와 똑같이 내가 속한
    채팅방인지 먼저 확인한다 — 이 검사가 없으면 남의 문자를 이 경로로 읽을 수 있다.
    """
    require_chat_membership(db, chat_id, current_user.id)

    if payload.message_id is not None:
        message = db.get(Message, payload.message_id)
        if message is None or message.chat_room_id != chat_id:
            raise api_error(404, "MESSAGE_NOT_FOUND", "선택한 문자를 찾을 수 없습니다.")
    else:
        message = (
            db.query(Message)
            .filter(Message.chat_room_id == chat_id)
            .order_by(Message.sent_at.desc(), Message.id.desc())
            .first()
        )
        if message is None:
            raise api_error(404, "MESSAGE_NOT_FOUND", "이 채팅방에는 분석할 문자가 없습니다.")

    analysis, session = run_analysis(
        db,
        user_id=current_user.id,
        message_text=message.content,
        chat_room_id=chat_id,
        message_id=message.id,
    )
    return ok(_to_response(analysis, session))


@router.get("/{analysis_id}")
def read_analysis(
    analysis_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """저장된 분석 결과를 다시 조회한다 (OF-05 탐지 기록 조회)."""
    analysis = _load_owned_analysis(db, analysis_id, current_user.id)
    return ok(_to_response(analysis, analysis.atm_session))


@router.get("/{analysis_id}/atm")
def read_atm_session(
    analysis_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """QR로 만들 ATM 세션 정보를 돌려준다 (QR에는 session_id만 넣는다)."""
    analysis = _load_owned_analysis(db, analysis_id, current_user.id)
    session = analysis.atm_session
    if session is None:
        raise api_error(404, "ATM_SESSION_NOT_FOUND", "ATM 세션이 아직 생성되지 않았습니다.")
    return ok(
        AtmSessionResponse(
            session_id=session.session_id,
            risk_level=analysis.risk_level,
            risk_score=analysis.risk_score,
            atm_status=session.atm_status,
        ).model_dump()
    )
