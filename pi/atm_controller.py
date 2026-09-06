"""ATM 상태 기계 — QR 인식 결과로 현금 배출을 허용/차단한다.

핵심 구현 조건 (PRD 5.4 / FR-09):
  DANGER 상태에서 출금 버튼을 눌러도 현금 배출 장치가 작동하지 않아야 한다.
그래서 배출 판단은 이 클래스 한 곳에만 두고, 액추에이터 호출은 그 판단을 통과한
경로에서만 일어난다.

qr-recognition-integration 스킬의 '로컬 판단 원칙':
  QR을 읽는 즉시 이 프로세스 안에서 판단한다. 서버 검증(PRD 필수)을 먼저 시도하되,
  네트워크가 끊겼고 QR에 risk_level이 들어 있으면 그 값으로 로컬 판단해 시연을
  이어간다 (PRD 11.3 '핵심 기능이 인터넷 연결 하나에만 의존하지 않는다').
"""
import asyncio
import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from backend_client import BackendClient, BackendUnavailableError, SessionNotFoundError

logger = logging.getLogger("atm_controller")

# ATM 상태값 (PRD 5.4)
STATE_READY = "READY"
STATE_WITHDRAW_ENABLED = "WITHDRAW_ENABLED"
STATE_WITHDRAW_BLOCKED = "WITHDRAW_BLOCKED"
STATE_CALL_CENTER = "CALL_CENTER"

# ATM 동작 (PRD 5.8)
ACTION_ALLOW = "ALLOW"
ACTION_VERIFY = "VERIFY"
ACTION_BLOCK = "BLOCK"

ACTION_TO_STATE: dict[str, str] = {
    ACTION_ALLOW: STATE_WITHDRAW_ENABLED,
    ACTION_VERIFY: STATE_WITHDRAW_BLOCKED,
    ACTION_BLOCK: STATE_WITHDRAW_BLOCKED,
}

RISK_TO_ACTION: dict[str, str] = {
    "SAFE": ACTION_ALLOW,
    "CAUTION": ACTION_VERIFY,
    "DANGER": ACTION_BLOCK,
}

# 순수 문자열 QR로 허용하는 session_id 형태 (예: VP-000003)
SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,50}$")

CASH_DISPENSER_DEVICE_ID = "cash_dispenser_1"
BUZZER_DEVICE_ID = "buzzer_1"
DISPENSER_DISPENSING = "DISPENSING"

# 콜센터 확인 결과 (PRD 8.3) — RELEASED는 서버가 action=ALLOW로 바꿔 주므로
# 이 파일에서는 '제한 유지' 쪽만 직접 구분하면 된다
RESOLUTION_MAINTAINED = "MAINTAINED"

# 노약자용 큰 글씨 안내 문구 (FR-10) — 화면은 이 문구를 그대로 크게 띄운다
GUIDANCE: dict[str, str] = {
    STATE_READY: "휴대폰 화면의 QR 코드를 카메라에 보여 주세요",
    STATE_WITHDRAW_ENABLED: "출금하실 금액을 선택해 주세요",
    STATE_WITHDRAW_BLOCKED: "보이스피싱 위험이 확인되어 현금 출금을 잠시 멈췄습니다",
    STATE_CALL_CENTER: "상담원이 확인 중입니다. 잠시만 기다려 주세요",
}

# 상담원이 보이스피싱으로 확정한 뒤에는 '기다려 주세요'라고 하면 안 된다 —
# 결론이 난 상태이므로 무엇을 해야 하는지 알려 준다 (FR-10 노약자 안내 원칙)
GUIDANCE_MAINTAINED = "보이스피싱으로 확인되어 현금 출금을 계속 제한합니다. 은행 창구로 가 주세요"


@dataclass
class QrPayload:
    """QR에서 읽어낸 값. PRD 6.2 기준으로 session_id만 필수다."""

    session_id: str
    risk_level: str | None = None


class InvalidQrError(ValueError):
    """QR 형식이 잘못됐거나 session_id가 없다 (TC-04)."""


def parse_qr_payload(raw: str) -> QrPayload:
    """QR 문자열을 파싱한다.

    허용 형태
      1) {"session_id": "VP-000003"}                      ← PRD 6.2 기본
      2) {"session_id": "...", "risk_level": "DANGER"}    ← 오프라인 백업용
      3) VP-000003                                         ← 순수 문자열
    """
    text = (raw or "").strip()
    if not text:
        raise InvalidQrError("QR 내용이 비어 있습니다.")

    if not text.startswith("{"):
        if not SESSION_ID_PATTERN.match(text):
            raise InvalidQrError("QR 데이터 형식이 올바르지 않습니다.")
        return QrPayload(session_id=text)

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise InvalidQrError("QR 데이터를 읽을 수 없습니다.") from exc
    if not isinstance(data, dict):
        raise InvalidQrError("QR 데이터 형식이 올바르지 않습니다.")

    session_id = str(data.get("session_id") or "").strip()
    if not session_id:
        raise InvalidQrError("QR에 session_id가 없습니다.")

    risk_level = data.get("risk_level")
    return QrPayload(
        session_id=session_id,
        risk_level=str(risk_level) if risk_level else None,
    )


class AtmController:
    """QR 인식 → 위험 판단 → 현금 배출 제어까지를 담당한다."""

    def __init__(self, provider: Any, backend: BackendClient | None = None) -> None:
        self._provider = provider
        self._backend = backend
        self.state: str = STATE_READY
        self.session_id: str | None = None
        self.risk_level: str | None = None
        self.risk_score: int | None = None
        self.reasons: list[str] = []
        self.summary: str = ""
        self.callcenter_resolution: str | None = None
        self.last_error: str | None = None
        self.offline: bool = False

    # ── 조회 ────────────────────────────────────────────────────────────────
    @property
    def guidance(self) -> str:
        """지금 화면에 크게 띄울 안내 문구."""
        if (
            self.state == STATE_WITHDRAW_BLOCKED
            and self.callcenter_resolution == RESOLUTION_MAINTAINED
        ):
            return GUIDANCE_MAINTAINED
        return GUIDANCE.get(self.state, "")

    def snapshot(self) -> dict[str, Any]:
        """7인치 터치 화면이 그대로 그릴 수 있는 현재 상태."""
        return {
            "state": self.state,
            "session_id": self.session_id,
            "risk_level": self.risk_level,
            "risk_score": self.risk_score,
            "reasons": self.reasons,
            "summary": self.summary,
            "guidance": self.guidance,
            "can_withdraw": self.state == STATE_WITHDRAW_ENABLED,
            "callcenter_resolution": self.callcenter_resolution,
            "last_error": self.last_error,
            "offline": self.offline,
        }

    def reset(self) -> None:
        """다음 사용자를 위해 대기 상태로 되돌린다."""
        self.state = STATE_READY
        self.session_id = None
        self.risk_level = None
        self.risk_score = None
        self.reasons = []
        self.summary = ""
        self.callcenter_resolution = None
        self.last_error = None
        self.offline = False

    # ── QR 인식 ─────────────────────────────────────────────────────────────
    async def handle_qr(self, raw: str) -> dict[str, Any]:
        """QR 한 건을 처리해 ATM 상태를 갱신한다."""
        try:
            payload = parse_qr_payload(raw)
        except InvalidQrError as exc:
            # 잘못된 QR은 거래 제어 데이터로 쓰지 않는다 (PRD 6.4 / TC-04)
            logger.warning("잘못된 QR: %s", exc)
            self.last_error = str(exc)
            return self.snapshot()

        verified = await self._verify(payload)
        if verified is None:
            return self.snapshot()

        self.session_id = payload.session_id
        self.risk_level = verified.get("risk_level")
        self.risk_score = verified.get("risk_score")
        self.reasons = list(verified.get("reasons") or [])
        self.summary = verified.get("summary") or ""
        self.callcenter_resolution = None  # 새 세션이므로 앞 사람의 확인 결과를 지운다
        self.last_error = None

        action = verified.get("action") or RISK_TO_ACTION.get(self.risk_level or "", ACTION_BLOCK)
        self.state = ACTION_TO_STATE.get(action, STATE_WITHDRAW_BLOCKED)

        if self.state == STATE_WITHDRAW_BLOCKED:
            await self._warn()

        await self._report_scan()
        return self.snapshot()

    async def _verify(self, payload: QrPayload) -> dict[str, Any] | None:
        """서버 검증을 먼저 시도하고, 네트워크가 끊겼을 때만 로컬 판단으로 넘어간다."""
        if self._backend is None:
            return self._local_verify(payload)

        try:
            verified = await asyncio.to_thread(self._backend.verify_session, payload.session_id)
        except SessionNotFoundError:
            # 서버가 모르는 QR — 위조/오래된 QR이므로 거래에 쓰지 않는다
            self.last_error = "등록되지 않은 QR입니다. 처음부터 다시 진행해 주세요."
            return None
        except (BackendUnavailableError, Exception) as exc:  # noqa: BLE001
            logger.warning("서버 검증 실패, 로컬 판단으로 전환합니다: %s", exc)
            self.offline = True
            return self._local_verify(payload)

        self.offline = False
        return verified

    def _local_verify(self, payload: QrPayload) -> dict[str, Any] | None:
        """네트워크 없이 QR에 들어 있는 risk_level만으로 판단한다 (백업 경로)."""
        if payload.risk_level not in RISK_TO_ACTION:
            self.last_error = "서버에 연결할 수 없어 위험 정보를 확인하지 못했습니다."
            return None
        return {
            "risk_level": payload.risk_level,
            "risk_score": None,
            "reasons": [],
            "summary": "오프라인 판단 (QR에 포함된 위험 등급 사용)",
            "action": RISK_TO_ACTION[payload.risk_level],
        }

    # ── 출금 ────────────────────────────────────────────────────────────────
    async def request_withdraw(self, amount: int | None = None) -> dict[str, Any]:
        """출금 버튼 처리. 여기가 FR-09를 지키는 유일한 관문이다."""
        if self.state != STATE_WITHDRAW_ENABLED:
            # 액추에이터를 아예 건드리지 않는다 — 배출 장치는 움직이지 않는다
            logger.info("출금 차단 (state=%s, session=%s)", self.state, self.session_id)
            await self._report_withdraw(dispensed=False)
            return {"dispensed": False, **self.snapshot()}

        await self._provider.set_actuator_state(
            CASH_DISPENSER_DEVICE_ID, DISPENSER_DISPENSING, value=amount, operator="user"
        )
        logger.info("현금 배출 (session=%s, amount=%s)", self.session_id, amount)
        await self._report_withdraw(dispensed=True)
        return {"dispensed": True, **self.snapshot()}

    # ── 콜센터 확인 폴링 ────────────────────────────────────────────────────
    async def enter_call_center(self) -> dict[str, Any]:
        """콜센터 확인 단계로 넘어간다 (제한은 유지된 상태)."""
        if self.state == STATE_WITHDRAW_BLOCKED:
            self.state = STATE_CALL_CENTER
            await self._report_scan()
        return self.snapshot()

    async def refresh_from_backend(self) -> dict[str, Any]:
        """콜센터 확인 결과를 반영한다.

        db-rules.md 경보성 디바이스 원칙: 제한은 시스템이 스스로 풀지 않는다.
        서버에 사람이 기록한 RELEASED가 있을 때만 출금이 다시 열린다.
        """
        if self._backend is None or self.session_id is None:
            return self.snapshot()
        try:
            status = await asyncio.to_thread(self._backend.read_session_status, self.session_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("세션 상태 폴링 실패: %s", exc)
            self.offline = True
            return self.snapshot()

        self.offline = False
        self.callcenter_resolution = status.get("callcenter_resolution")
        action = status.get("action", ACTION_BLOCK)
        if action == ACTION_ALLOW:
            self.state = STATE_WITHDRAW_ENABLED
        elif self.callcenter_resolution == RESOLUTION_MAINTAINED:
            # 상담원이 보이스피싱으로 확정했다. 결론이 났는데 계속 '확인 중'을
            # 띄워 두면 어르신은 끝없이 기다리게 된다 — 차단 상태로 되돌린다.
            self.state = STATE_WITHDRAW_BLOCKED
        elif self.state == STATE_WITHDRAW_ENABLED:
            # 서버가 다시 막았다면 즉시 반영한다
            self.state = STATE_WITHDRAW_BLOCKED
        return self.snapshot()

    # ── 보고 (실패해도 ATM 동작은 계속된다) ─────────────────────────────────
    async def _report_scan(self) -> None:
        if self._backend is None or self.session_id is None:
            return
        try:
            await asyncio.to_thread(self._backend.report_scan, self.session_id, self.state)
        except Exception as exc:  # noqa: BLE001
            logger.warning("스캔 보고 실패(무시하고 계속): %s", exc)

    async def _report_withdraw(self, *, dispensed: bool) -> None:
        if self._backend is None or self.session_id is None:
            return
        try:
            await asyncio.to_thread(
                self._backend.report_withdraw_attempt, self.session_id, dispensed
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("출금 시도 보고 실패(무시하고 계속): %s", exc)

    async def _warn(self) -> None:
        """위험 상태에서 부저를 울린다 (선택 기능 — 부저가 없으면 조용히 넘어간다)."""
        try:
            await self._provider.set_actuator_state(BUZZER_DEVICE_ID, "ON", operator="device")
        except Exception as exc:  # noqa: BLE001
            logger.debug("부저 없음 또는 제어 실패: %s", exc)
