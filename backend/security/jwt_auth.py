"""사용자향 인증 — JWT (api-rules.md '인증 분리').

이 모듈은 대시보드/앱에서 호출하는 사용자향 엔드포인트에만 쓴다.
라즈베리파이 등 디바이스향 엔드포인트에는 절대 쓰지 않는다 (device_auth.py 사용).
"""
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, Header
from fastapi.exceptions import HTTPException
from sqlalchemy.orm import Session

from api_responses import api_error
from config import get_settings
from db.database import get_db
from db.models import ROLE_AGENT, User

_BEARER_PREFIX = "bearer "


def create_access_token(user: User) -> str:
    """로그인 성공 시 발급할 액세스 토큰을 만든다."""
    settings = get_settings()
    if not settings.jwt_secret:
        raise api_error(500, "JWT_SECRET_MISSING", "서버에 JWT_SECRET이 설정되지 않았습니다.")

    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": str(user.id), "username": user.username, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    """토큰의 서명과 만료를 검증해 payload를 돌려준다. 실패하면 401."""
    settings = get_settings()
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError:
        raise api_error(401, "TOKEN_EXPIRED", "로그인이 만료되었습니다. 다시 로그인해 주세요.")
    except jwt.PyJWTError:
        raise api_error(401, "INVALID_TOKEN", "유효하지 않은 토큰입니다.")


def _user_id_from_payload(payload: dict) -> int | None:
    """payload의 sub를 사용자 id로 바꾼다. 숫자가 아니면 None."""
    try:
        return int(payload.get("sub", ""))
    except (TypeError, ValueError):
        return None


def get_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    """Authorization: Bearer <JWT> 헤더를 검증하고 사용자를 돌려준다."""
    if not authorization or not authorization.lower().startswith(_BEARER_PREFIX):
        raise api_error(401, "UNAUTHORIZED", "Authorization: Bearer <JWT> 헤더가 필요합니다.")

    payload = decode_access_token(authorization[len(_BEARER_PREFIX):].strip())
    user_id = _user_id_from_payload(payload)
    user = db.get(User, user_id) if user_id is not None else None
    if user is None:
        raise api_error(401, "USER_NOT_FOUND", "토큰의 사용자를 찾을 수 없습니다.")
    return user


def require_callcenter_agent(current_user: User = Depends(get_current_user)) -> User:
    """콜센터 화면 전용 — 상담원 계정만 통과시킨다.

    PRD 8: 자동 판정을 뒤집는 최종 확인은 사용자 본인이 아니라 사람(상담원)이 한다.
    이 검사가 없으면 제한을 받은 사용자가 스스로 제한을 풀 수 있다.
    """
    if current_user.role != ROLE_AGENT:
        raise api_error(403, "FORBIDDEN", "콜센터 상담원 계정만 접근할 수 있습니다.")
    return current_user


def agent_from_token(db: Session, token: str | None) -> User | None:
    """토큰이 상담원 계정의 것이면 그 사용자를, 아니면 None을 돌려준다.

    WebSocket 핸드셰이크는 HTTPException으로 응답할 수 없어서 의존성(Depends)
    대신 이 함수를 쓴다. 그래서 예외를 던지지 않고 None으로만 알린다.
    """
    if not token:
        return None
    try:
        payload = decode_access_token(token)
    except HTTPException:
        return None

    user_id = _user_id_from_payload(payload)
    user = db.get(User, user_id) if user_id is not None else None
    if user is None or user.role != ROLE_AGENT:
        return None
    return user
