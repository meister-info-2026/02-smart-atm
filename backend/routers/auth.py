"""인증 라우터 — 사용자향 (JWT 발급)."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api_responses import api_error, ok
from db.database import get_db
from db.models import User
from schemas.models import LoginRequest, TokenResponse
from security.jwt_auth import create_access_token
from security.passwords import verify_password

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/login")
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> dict:
    """아이디/비밀번호로 로그인하고 JWT 액세스 토큰을 받는다."""
    user = db.query(User).filter(User.username == payload.username).first()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise api_error(401, "INVALID_CREDENTIALS", "아이디 또는 비밀번호가 올바르지 않습니다.")
    token = create_access_token(user)
    return ok(TokenResponse(access_token=token).model_dump())
