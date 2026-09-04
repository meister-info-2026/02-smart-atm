"""디바이스향 인증 — X-Device-Api-Key (api-rules.md '인증 분리').

라즈베리파이 ATM처럼 사람이 로그인할 수 없는 클라이언트 전용이다.
사용자향 엔드포인트에는 절대 쓰지 않는다 (jwt_auth.py 사용).
"""
import hmac

from fastapi import Header

from api_responses import api_error
from config import get_settings


def require_device_key(x_device_api_key: str | None = Header(default=None)) -> str:
    """디바이스 API 키를 상수 시간 비교로 검증한다."""
    settings = get_settings()
    if not settings.device_api_key:
        raise api_error(500, "DEVICE_KEY_MISSING", "서버에 DEVICE_API_KEY가 설정되지 않았습니다.")
    if not x_device_api_key or not hmac.compare_digest(x_device_api_key, settings.device_api_key):
        raise api_error(401, "UNAUTHORIZED_DEVICE", "유효한 X-Device-Api-Key 헤더가 필요합니다.")
    return x_device_api_key
