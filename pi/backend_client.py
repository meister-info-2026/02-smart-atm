"""백엔드 REST 호출 래퍼 (디바이스향 인증).

api-rules.md: 라즈베리파이는 X-Device-Api-Key 헤더로만 인증한다.
hardware-rules.md: 파이가 백엔드로 pull 한다 (백엔드가 파이에 push 하지 않는다).
"""
import logging
import os
from typing import Any

import requests

logger = logging.getLogger("backend_client")

REQUEST_TIMEOUT_SECONDS = 5


class BackendUnavailableError(RuntimeError):
    """백엔드에 닿지 못했을 때 (네트워크 장애). 세션 자체가 없는 경우와 구분한다."""


class SessionNotFoundError(RuntimeError):
    """서버가 모르는 session_id — 잘못된 QR이다 (TC-04)."""


class BackendClient:
    """ATM이 쓰는 백엔드 API 클라이언트."""

    def __init__(self, base_url: str | None = None, api_key: str | None = None) -> None:
        self.base_url = (base_url or os.getenv("BACKEND_URL", "http://localhost:8000")).rstrip("/")
        self.api_key = api_key or os.getenv("DEVICE_API_KEY", "")
        self._headers = {"X-Device-Api-Key": self.api_key}

    def _get(self, path: str) -> dict[str, Any]:
        try:
            response = requests.get(
                f"{self.base_url}{path}", headers=self._headers, timeout=REQUEST_TIMEOUT_SECONDS
            )
        except requests.RequestException as exc:
            raise BackendUnavailableError(f"백엔드에 연결하지 못했습니다: {exc}") from exc
        if response.status_code == 404:
            raise SessionNotFoundError(f"서버에 없는 세션입니다: {path}")
        response.raise_for_status()
        return response.json()["data"]

    def _post(self, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            response = requests.post(
                f"{self.base_url}{path}",
                headers=self._headers,
                json=payload,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
        except requests.RequestException as exc:
            raise BackendUnavailableError(f"백엔드에 연결하지 못했습니다: {exc}") from exc
        if response.status_code == 404:
            raise SessionNotFoundError(f"서버에 없는 세션입니다: {path}")
        response.raise_for_status()
        return response.json()["data"]

    def verify_session(self, session_id: str) -> dict[str, Any]:
        """QR에서 읽은 session_id로 위험 정보를 서버에서 조회한다 (OF-03 필수)."""
        return self._get(f"/api/v1/atm/verify/{session_id}")

    def report_scan(self, session_id: str, atm_status: str) -> dict[str, Any]:
        """QR 인식 결과와 전환된 상태를 보고한다."""
        return self._post("/api/v1/atm/scan", {"session_id": session_id, "atm_status": atm_status})

    def read_session_status(self, session_id: str) -> dict[str, Any]:
        """콜센터 확인 결과를 폴링한다."""
        return self._get(f"/api/v1/atm/session-status/{session_id}")

    def report_withdraw_attempt(self, session_id: str, dispensed: bool) -> dict[str, Any]:
        """출금 버튼을 눌렀을 때 실제 배출 여부를 보고한다 (FR-08/FR-09 근거)."""
        return self._post(
            f"/api/v1/atm/withdraw-attempt/{session_id}?dispensed={str(dispensed).lower()}"
        )
