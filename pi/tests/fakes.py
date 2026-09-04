"""pi 테스트용 공용 더블 — 백엔드 응답을 흉내 낸다."""
from backend_client import BackendUnavailableError, SessionNotFoundError

SAFE_SESSION = "VP-000001"
DANGER_SESSION = "VP-000002"
CAUTION_SESSION = "VP-000003"


class FakeBackend:
    """백엔드 응답을 흉내 내는 테스트 더블."""

    def __init__(self) -> None:
        self.sessions = {
            SAFE_SESSION: {
                "session_id": SAFE_SESSION, "risk_level": "SAFE", "risk_score": 0,
                "action": "ALLOW", "reasons": [], "summary": "",
            },
            DANGER_SESSION: {
                "session_id": DANGER_SESSION, "risk_level": "DANGER", "risk_score": 100,
                "action": "BLOCK", "reasons": ["기관 사칭 표현 감지"], "summary": "기관 사칭 감지",
            },
            CAUTION_SESSION: {
                "session_id": CAUTION_SESSION, "risk_level": "CAUTION", "risk_score": 45,
                "action": "VERIFY", "reasons": ["긴급 행동 요구 감지"], "summary": "긴급 요구 감지",
            },
        }
        self.status_action: dict[str, str] = {}
        self.scans: list[tuple[str, str]] = []
        self.withdraw_reports: list[tuple[str, bool]] = []
        self.unavailable = False

    def verify_session(self, session_id: str) -> dict:
        if self.unavailable:
            raise BackendUnavailableError("네트워크 끊김")
        if session_id not in self.sessions:
            raise SessionNotFoundError(session_id)
        return self.sessions[session_id]

    def report_scan(self, session_id: str, atm_status: str) -> dict:
        self.scans.append((session_id, atm_status))
        return {}

    def read_session_status(self, session_id: str) -> dict:
        return {
            "session_id": session_id,
            "action": self.status_action.get(session_id, "BLOCK"),
            "atm_status": "WITHDRAW_BLOCKED",
            "callcenter_resolution": None,
        }

    def report_withdraw_attempt(self, session_id: str, dispensed: bool) -> dict:
        self.withdraw_reports.append((session_id, dispensed))
        return {}
