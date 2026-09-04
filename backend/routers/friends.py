"""친구 라우터 — 사용자향 (JWT 필요)."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api_responses import ok
from db.database import get_db
from db.models import Friendship, User
from schemas.models import FriendResponse
from security.jwt_auth import get_current_user

router = APIRouter(prefix="/api/v1/friends", tags=["friends"])


@router.get("")
def list_friends(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """내 친구 목록을 돌려준다."""
    rows = (
        db.query(User)
        .join(Friendship, Friendship.friend_user_id == User.id)
        .filter(Friendship.user_id == current_user.id)
        .order_by(User.display_name)
        .all()
    )
    return ok(
        [
            FriendResponse(id=u.id, username=u.username, display_name=u.display_name).model_dump()
            for u in rows
        ]
    )
