"""API 응답 형식 헬퍼 (api-rules.md).

성공: {"data": ...}
실패: {"error": {"code": "...", "message": "..."}}
"""
from typing import Any

from fastapi import HTTPException


def ok(data: Any) -> dict[str, Any]:
    """성공 응답을 감싼다."""
    return {"data": data}


def api_error(status_code: int, code: str, message: str) -> HTTPException:
    """실패 응답 형식을 지키는 HTTPException을 만든다."""
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
    )
