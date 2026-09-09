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
import math
import os
import re
import time
from dataclasses import dataclass
from typing import Any

from backend_client import (
    BackendClient,
    BackendUnavailableError,
    DeviceAuthError,
    SessionNotFoundError,
)

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

# 출금이 되는 상태들. READY가 여기 들어 있는 것이 이 기계의 성격을 정한다 —
# ATM은 공용 기계다. 지금 그 앞에 선 사람은 앱을 쓴 당사자일 수도, 가족일 수도,
# 이 시스템과 아무 상관 없는 사람일 수도 있다. QR을 못 내민다고 출금을 막으면
# 그건 ATM이 아니라 QR 판독기다. 평상시에는 그냥 돈이 나오고, **위험이 확인된
# 세션에서만** 막는다 (PRD: "평범한 문자는 시스템이 건드리지 않는다").
DISPENSING_STATES: frozenset[str] = frozenset({STATE_READY, STATE_WITHDRAW_ENABLED})

# 노약자용 큰 글씨 안내 문구 (FR-10) — 화면은 이 문구를 그대로 크게 띄운다
GUIDANCE: dict[str, str] = {
    STATE_READY: "출금하실 금액을 선택해 주세요",
    STATE_WITHDRAW_ENABLED: "출금하실 금액을 선택해 주세요",
    STATE_WITHDRAW_BLOCKED: "보이스피싱 위험이 확인되어 현금 출금을 잠시 멈췄습니다",
    STATE_CALL_CENTER: "상담원이 확인 중입니다. 잠시만 기다려 주세요",
}

# 상담원이 보이스피싱으로 확정한 뒤에는 '기다려 주세요'라고 하면 안 된다 —
# 결론이 난 상태이므로 무엇을 해야 하는지 알려 준다 (FR-10 노약자 안내 원칙)
GUIDANCE_MAINTAINED = "보이스피싱으로 확인되어 현금 출금을 계속 제한합니다. 은행 창구로 가 주세요"

# 설정이 잘못돼 서버 검증을 못 하는 상태. 어르신께는 기술적인 원인 대신 무엇을 해야
# 하는지만 알려 주고, 진짜 원인은 로그에 남긴다 (관리자가 볼 곳은 로그다).
# 다음 사람을 위한 자동 초기화. ATM은 공용 기계인데 앞사람이 남긴 화면이 계속
# 떠 있으면, 뒤에 온 사람이 남의 차단을 물려받는다. 부스에서도 관람객마다
# '처음으로'를 눌러 줄 수 없다.
#
# 이건 세션의 차단을 푸는 것이 아니다 — 차단은 서버에 그대로 남아 있고, 같은 QR을
# 다시 비추면 즉시 다시 막힌다. 여기서 하는 일은 '기계를 다음 사람에게 넘기는 것'뿐이다.
IDLE_RESET_SECONDS = int(os.getenv("IDLE_RESET_SECONDS", "60"))

ERROR_DEVICE_AUTH = "지금은 이 ATM을 사용할 수 없습니다. 은행 직원에게 알려 주세요"
ERROR_VERIFY_FAILED = "위험 정보를 확인하지 못했습니다. 처음부터 다시 진행해 주세요"

# 위 문구는 어르신용이라 원인을 담지 않는다. 그런데 부스를 운영하는 사람은 화면만
# 보고 있다 — 원인을 알려면 데몬 터미널을 봐야 한다는 걸 모르면 한참을 헤맨다.
# 그래서 화면 구석에 '고치는 사람용' 한 줄을 따로 띄운다.
HINT_DEVICE_AUTH = "설정 오류: DEVICE_API_KEY 불일치 — backend/.env와 pi/.env를 같게 맞추고 데몬을 다시 켜세요"
HINT_VERIFY_FAILED = "서버 응답을 처리하지 못했습니다 — ATM 데몬 터미널의 로그를 확인하세요"


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

    def __init__(
        self,
        provider: Any,
        backend: BackendClient | None = None,
        idle_reset_seconds: int | None = None,
    ) -> None:
        self._provider = provider
        self._backend = backend
        self._idle_reset_seconds = (
            IDLE_RESET_SECONDS if idle_reset_seconds is None else idle_reset_seconds
        )
        self._last_touch: float = time.monotonic()
        self.state: str = STATE_READY
        self.session_id: str | None = None
        self.risk_level: str | None = None
        self.risk_score: int | None = None
        self.reasons: list[str] = []
        self.summary: str = ""
        self.callcenter_resolution: str | None = None
        self.last_error: str | None = None
        self.operator_hint: str | None = None
        self.offline: bool = False

    # ── 다음 사람에게 넘기기 ────────────────────────────────────────────────
    def touch(self) -> None:
        """사람이 무언가를 했다 — 자동 초기화 시계를 처음으로 되돌린다."""
        self._last_touch = time.monotonic()

    @property
    def idle_reset_in(self) -> int | None:
        """자동 초기화까지 남은 초. 셀 필요가 없으면 None.

        세지 않는 두 경우가 있다.
          - 아직 아무 일도 없었던 평상시: 되돌릴 것이 없다.
          - 상담원 확인을 기다리는 중: 이건 노는 게 아니라 **사람을 기다리는**
            시간이다. 여기서 시계를 돌리면 확인이 오기도 전에 상담 자체가
            사라지고, 시연 중에는 설명하는 사이에 화면이 저절로 초기화된다.
        """
        if self._idle_reset_seconds <= 0:
            return None
        if self.state == STATE_CALL_CENTER:
            return None
        if self.session_id is None and self.last_error is None:
            return None
        elapsed = time.monotonic() - self._last_touch
        # 올림으로 센다. 반올림하면 아직 0.4초 남았는데 "0초"로 보이고, 그 0을
        # 본 순간 초기화가 일어나 화면이 1초 먼저 사라진 것처럼 보인다.
        return max(0, math.ceil(self._idle_reset_seconds - elapsed))

    def reset_if_idle(self) -> bool:
        """시간이 다 됐으면 대기 상태로 돌려놓는다. 실제로 되돌렸으면 True."""
        remaining = self.idle_reset_in
        if remaining is None or remaining > 0:
            return False
        logger.info("무동작 %d초 — 다음 사용자를 위해 초기화합니다", self._idle_reset_seconds)
        self.reset()
        return True

    # ── 조회 ────────────────────────────────────────────────────────────────
    @property
    def can_dispense(self) -> bool:
        """지금 이 사람에게 현금을 내줘도 되는가.

        두 가지를 함께 본다.

        1) 상태 — 위험이 확인된 세션(BLOCKED/CALL_CENTER)은 당연히 안 된다.
        2) 확인 실패 여부 — 누군가 QR을 내밀었는데 우리가 확인하지 못한 경우
           (등록되지 않은 QR, 디바이스 키 오류, 원인 불명)에는 내주지 않는다.
           확인을 못 했다는 것은 '안전하다'는 뜻이 아니다. 특히 키 설정이 틀려
           서버에 못 물어보는 상태라면 위험한 세션도 통과시키게 되므로, 보호
           장치가 꺼진 채 돈이 나가는 일만은 막아야 한다.

        아무도 확인을 요청하지 않은 평상시(READY, 오류 없음)에는 보통 ATM처럼
        돈이 나온다 — 지나가던 제삼자까지 막지 않기 위해서다.
        """
        return self.state in DISPENSING_STATES and self.last_error is None

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
            "can_withdraw": self.can_dispense,
            "callcenter_resolution": self.callcenter_resolution,
            "last_error": self.last_error,
            "operator_hint": self.operator_hint,
            "idle_reset_in": self.idle_reset_in,
            "offline": self.offline,
        }

    def reset(self) -> None:
        """다음 사용자를 위해 대기 상태로 되돌린다."""
        self.touch()
        self.state = STATE_READY
        self.session_id = None
        self.risk_level = None
        self.risk_score = None
        self.reasons = []
        self.summary = ""
        self.callcenter_resolution = None
        self.last_error = None
        self.operator_hint = None
        self.offline = False

    # ── QR 인식 ─────────────────────────────────────────────────────────────
    async def handle_qr(self, raw: str) -> dict[str, Any]:
        """QR 한 건을 처리해 ATM 상태를 갱신한다."""
        self.touch()
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
        self.operator_hint = None

        action = verified.get("action") or RISK_TO_ACTION.get(self.risk_level or "", ACTION_BLOCK)
        self.state = ACTION_TO_STATE.get(action, STATE_WITHDRAW_BLOCKED)

        if self.state == STATE_WITHDRAW_BLOCKED:
            await self._warn()

        await self._report_scan()
        return self.snapshot()

    async def _verify(self, payload: QrPayload) -> dict[str, Any] | None:
        """서버 검증을 먼저 시도한다.

        로컬 판단으로 넘어가는 경우는 **서버에 닿지 못했을 때 하나뿐이다**(PRD 11.3).
        서버가 대답을 했는데 그 대답이 마음에 안 든다고 QR을 믿기 시작하면, QR이
        스스로 적어 온 위험 등급이 서버 판정을 이기게 된다 — 그건 검증이 아니다.
        """
        if self._backend is None:
            return self._local_verify(payload)

        try:
            verified = await asyncio.to_thread(self._backend.verify_session, payload.session_id)
        except SessionNotFoundError:
            # 서버가 모르는 QR — 위조/오래된 QR이므로 거래에 쓰지 않는다
            self.last_error = "등록되지 않은 QR입니다. 처음부터 다시 진행해 주세요."
            return None
        except DeviceAuthError as exc:
            # 서버는 살아 있고 이 ATM을 거부한 것이다. 장애가 아니라 설정 오류이므로
            # 오프라인으로 넘어가지 않고 멈춘다 (키 오타 하나로 현금이 나가면 안 된다).
            logger.error("디바이스 인증 실패 — 설정을 고쳐야 합니다: %s", exc)
            self.last_error = ERROR_DEVICE_AUTH
            self.operator_hint = HINT_DEVICE_AUTH
            return None
        except BackendUnavailableError as exc:
            # 여기가 유일한 백업 경로다 — 서버에 정말 닿지 못했을 때
            logger.warning("서버에 연결하지 못해 로컬 판단으로 전환합니다: %s", exc)
            self.offline = True
            return self._local_verify(payload)
        except Exception as exc:  # noqa: BLE001
            # 원인을 모르는 실패. 서버에 닿았는지조차 확신할 수 없으니 QR을 믿지 않는다.
            # (ATM 전체가 죽지는 않게 잡되, 거래는 열지 않는다)
            logger.exception("서버 검증 중 예상하지 못한 오류: %s", exc)
            self.last_error = ERROR_VERIFY_FAILED
            self.operator_hint = HINT_VERIFY_FAILED
            return None

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
        """출금 버튼 처리. 여기가 FR-09를 지키는 유일한 관문이다.

        막는 것은 '위험이 확인된 세션'이지 '확인되지 않은 사람'이 아니다.
        평상시(READY)에는 보통 ATM처럼 돈이 나온다.
        """
        self.touch()
        if not self.can_dispense:
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
        self.touch()
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
        except DeviceAuthError as exc:
            # 폴링도 마찬가지다. '오프라인'이라고 표시하면 멀쩡한 서버를 뒤지게 된다.
            logger.error("디바이스 인증 실패 — 설정을 고쳐야 합니다: %s", exc)
            self.last_error = ERROR_DEVICE_AUTH
            self.operator_hint = HINT_DEVICE_AUTH
            return self.snapshot()  # 제한은 그대로 유지된다
        except Exception as exc:  # noqa: BLE001
            logger.warning("세션 상태 폴링 실패: %s", exc)
            self.offline = True
            return self.snapshot()

        self.offline = False
        was_waiting = self.state == STATE_CALL_CENTER
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
        if was_waiting and self.state != STATE_CALL_CENTER:
            # 상담원이 답을 줬다. 기다림이 끝났으니 이제부터 자동 초기화 시계가 돈다
            self.touch()
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
