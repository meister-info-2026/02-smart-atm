"""사용자 라우터 — 사용자향 (JWT 필요)."""
from fastapi import APIRouter, Depends

from api_responses import ok
from db.models import User
from schemas.models import UserResponse
from security.jwt_auth import get_current_user

router = APIRouter(prefix="/api/v1/users", tags=["users"])


@router.get("/me")
def read_me(current_user: User = Depends(get_current_user)) -> dict:
    """로그인한 사용자 정보를 돌려준다."""
    return ok(
        UserResponse(
            id=current_user.id,
            username=current_user.username,
            display_name=current_user.display_name,
            role=current_user.role,
        ).model_dump()
    )
