"""헬스체크 라우터 (PRD 5.8 확정 API)."""
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from api_responses import ok
from config import get_settings
from db.database import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    """서버가 떠 있는지 확인한다."""
    settings = get_settings()
    return ok({"status": "ok", "device_mode": settings.device_mode})


@router.get("/health/db")
def health_db(db: Session = Depends(get_db)) -> dict:
    """DB 접속이 살아 있는지 확인한다."""
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:  # 조용히 삼키지 않는다 (coding-standards.md)
        return ok({"status": "error", "detail": str(exc)})
    return ok({"status": "ok"})
