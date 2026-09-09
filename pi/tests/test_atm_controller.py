"""ATM 상태 기계 테스트.

가장 중요한 것은 FR-09다 — DANGER 상태에서 출금 버튼을 눌러도 현금 배출 장치가
'실제로 동작하지 않는지'를 Mock Provider의 배출 카운터로 직접 확인한다.
"""
import asyncio
import time

import pytest

from atm_controller import (
    STATE_CALL_CENTER,
    STATE_READY,
    STATE_WITHDRAW_BLOCKED,
    STATE_WITHDRAW_ENABLED,
    AtmController,
    InvalidQrError,
    parse_qr_payload,
)
from fakes import CAUTION_SESSION, DANGER_SESSION, SAFE_SESSION, FakeBackend
from iot.mock_provider import MockDeviceProvider


@pytest.fixture
def provider() -> MockDeviceProvider:
    return MockDeviceProvider()


@pytest.fixture
def backend() -> FakeBackend:
    return FakeBackend()


@pytest.fixture
def controller(provider: MockDeviceProvider, backend: FakeBackend) -> AtmController:
    return AtmController(provider, backend)


# ── QR 파싱 (PRD 6.2 / 6.4) ─────────────────────────────────────────────────
def test_parse_session_id_only_payload() -> None:
    """PRD 6.2 기본 형태: QR에는 session_id만 들어간다."""
    payload = parse_qr_payload('{"session_id": "VP-000003"}')
    assert payload.session_id == "VP-000003"
    assert payload.risk_level is None


def test_parse_plain_string_payload() -> None:
    assert parse_qr_payload("VP-000003").session_id == "VP-000003"


def test_parse_payload_with_risk_level_for_offline_backup() -> None:
    payload = parse_qr_payload('{"session_id": "VP-000002", "risk_level": "DANGER"}')
    assert payload.risk_level == "DANGER"


@pytest.mark.parametrize("raw", ["", "   ", "{not json", "{}", '{"session_id": ""}', "[1,2]"])
def test_parse_rejects_broken_payloads(raw: str) -> None:
    """TC-04: 잘못된 QR / 데이터 누락은 거부한다."""
    with pytest.raises(InvalidQrError):
        parse_qr_payload(raw)


# ── FR-08 정상 상태 출금 ────────────────────────────────────────────────────
def test_safe_qr_enables_withdrawal_and_dispenses(
    controller: AtmController, provider: MockDeviceProvider
) -> None:
    """SAFE → WITHDRAW_ENABLED → 출금 버튼에 배출 장치가 실제로 동작한다."""
    snapshot = asyncio.run(controller.handle_qr(f'{{"session_id": "{SAFE_SESSION}"}}'))
    assert snapshot["state"] == STATE_WITHDRAW_ENABLED
    assert snapshot["can_withdraw"] is True

    result = asyncio.run(controller.request_withdraw(50000))
    assert result["dispensed"] is True
    assert provider.dispense_count == 1


# ── FR-09 위험 상태 출금 차단 (핵심 구현 조건) ──────────────────────────────
def test_danger_qr_blocks_withdrawal_and_never_moves_servo(
    controller: AtmController, provider: MockDeviceProvider, backend: FakeBackend
) -> None:
    """DANGER 상태에서 출금 버튼을 여러 번 눌러도 배출 장치는 한 번도 동작하지 않는다."""
    snapshot = asyncio.run(controller.handle_qr(f'{{"session_id": "{DANGER_SESSION}"}}'))
    assert snapshot["state"] == STATE_WITHDRAW_BLOCKED
    assert snapshot["can_withdraw"] is False
    assert snapshot["reasons"] == ["기관 사칭 표현 감지"]

    for _ in range(3):
        result = asyncio.run(controller.request_withdraw(50000))
        assert result["dispensed"] is False

    assert provider.dispense_count == 0, "위험 상태에서 현금 배출 장치가 동작하면 안 된다"
    assert backend.withdraw_reports == [(DANGER_SESSION, False)] * 3


def test_caution_qr_maps_to_verify_and_blocks_for_now(
    controller: AtmController, provider: MockDeviceProvider
) -> None:
    """PRD 9.3: CAUTION은 추가 확인이 필요한 상태 — 그대로 출금을 열지 않는다."""
    snapshot = asyncio.run(controller.handle_qr(f'{{"session_id": "{CAUTION_SESSION}"}}'))
    assert snapshot["state"] == STATE_WITHDRAW_BLOCKED
    asyncio.run(controller.request_withdraw())
    assert provider.dispense_count == 0


# ── TC-04 잘못된 QR ─────────────────────────────────────────────────────────
def test_unknown_session_is_not_used_as_control_data(
    controller: AtmController, provider: MockDeviceProvider
) -> None:
    """서버가 모르는 QR은 거래 제어에 쓰지 않고 오류만 안내한다."""
    snapshot = asyncio.run(controller.handle_qr('{"session_id": "VP-999999"}'))
    assert snapshot["state"] == STATE_READY
    assert snapshot["session_id"] is None
    assert "등록되지 않은" in (snapshot["last_error"] or "")
    assert provider.dispense_count == 0


def test_broken_qr_keeps_previous_state(controller: AtmController) -> None:
    snapshot = asyncio.run(controller.handle_qr("{쓰레기}"))
    assert snapshot["state"] == STATE_READY
    assert snapshot["last_error"]


# ── 콜센터 확인 (PRD 8.3 / TC-05) ───────────────────────────────────────────
def test_call_center_release_reopens_withdrawal(
    controller: AtmController, backend: FakeBackend
) -> None:
    """상담원이 RELEASED를 기록해야만 출금이 다시 열린다."""
    asyncio.run(controller.handle_qr(f'{{"session_id": "{DANGER_SESSION}"}}'))
    asyncio.run(controller.enter_call_center())
    assert controller.state == STATE_CALL_CENTER

    # 아직 아무도 확인하지 않았으면 계속 막혀 있다
    asyncio.run(controller.refresh_from_backend())
    assert controller.state != STATE_WITHDRAW_ENABLED

    backend.status_action[DANGER_SESSION] = "ALLOW"
    asyncio.run(controller.refresh_from_backend())
    assert controller.state == STATE_WITHDRAW_ENABLED


def test_system_never_unblocks_itself(controller: AtmController) -> None:
    """db-rules.md 경보성 디바이스 원칙: 폴링을 반복해도 스스로 풀리지 않는다."""
    asyncio.run(controller.handle_qr(f'{{"session_id": "{DANGER_SESSION}"}}'))
    for _ in range(5):
        asyncio.run(controller.refresh_from_backend())
    assert controller.state == STATE_WITHDRAW_BLOCKED


# ── 네트워크 장애 백업 경로 (PRD 11.3) ──────────────────────────────────────
def test_offline_falls_back_to_qr_risk_level(
    controller: AtmController, backend: FakeBackend, provider: MockDeviceProvider
) -> None:
    """서버가 죽어도 QR에 risk_level이 있으면 로컬 판단으로 시연을 이어간다."""
    backend.unavailable = True
    snapshot = asyncio.run(
        controller.handle_qr(f'{{"session_id": "{DANGER_SESSION}", "risk_level": "DANGER"}}')
    )
    assert snapshot["offline"] is True
    assert snapshot["state"] == STATE_WITHDRAW_BLOCKED
    asyncio.run(controller.request_withdraw())
    assert provider.dispense_count == 0


def test_offline_without_risk_level_refuses_to_guess(
    controller: AtmController, backend: FakeBackend
) -> None:
    """서버도 못 닿고 QR에도 위험 정보가 없으면 추측하지 않고 오류로 남긴다."""
    backend.unavailable = True
    snapshot = asyncio.run(controller.handle_qr(f'{{"session_id": "{DANGER_SESSION}"}}'))
    assert snapshot["state"] == STATE_READY
    assert "서버에 연결할 수 없어" in (snapshot["last_error"] or "")


def test_reset_returns_to_ready(controller: AtmController) -> None:
    asyncio.run(controller.handle_qr(f'{{"session_id": "{DANGER_SESSION}"}}'))
    controller.reset()
    assert controller.snapshot()["state"] == STATE_READY
    assert controller.snapshot()["session_id"] is None


def test_call_center_maintain_stops_saying_please_wait(
    controller: AtmController, backend: FakeBackend
) -> None:
    """상담원이 '보이스피싱 — 제한 유지'를 누르면 '확인 중' 화면에서 빠져나온다.

    결론이 났는데도 "상담원이 확인 중입니다. 잠시만 기다려 주세요"를 계속 띄우면
    어르신은 끝나지 않을 기다림을 하게 된다 (FR-10).
    """
    asyncio.run(controller.handle_qr(f'{{"session_id": "{DANGER_SESSION}"}}'))
    asyncio.run(controller.enter_call_center())
    assert controller.state == STATE_CALL_CENTER

    backend.status_resolution[DANGER_SESSION] = "MAINTAINED"
    snapshot = asyncio.run(controller.refresh_from_backend())

    assert snapshot["state"] == STATE_WITHDRAW_BLOCKED
    assert snapshot["callcenter_resolution"] == "MAINTAINED"
    assert "기다려" not in snapshot["guidance"]
    assert "계속 제한" in snapshot["guidance"]


def test_maintained_session_still_never_dispenses(
    controller: AtmController, backend: FakeBackend, provider: MockDeviceProvider
) -> None:
    """제한 유지로 확정된 뒤에도 출금 버튼은 여전히 아무것도 배출하지 않는다."""
    asyncio.run(controller.handle_qr(f'{{"session_id": "{DANGER_SESSION}"}}'))
    asyncio.run(controller.enter_call_center())
    backend.status_resolution[DANGER_SESSION] = "MAINTAINED"
    asyncio.run(controller.refresh_from_backend())

    asyncio.run(controller.request_withdraw(500000))
    assert provider.dispense_count == 0


def test_new_qr_clears_previous_callcenter_result(
    controller: AtmController, backend: FakeBackend
) -> None:
    """다음 사람의 QR을 읽으면 앞 사람의 콜센터 확인 결과를 끌고 가지 않는다."""
    asyncio.run(controller.handle_qr(f'{{"session_id": "{DANGER_SESSION}"}}'))
    backend.status_resolution[DANGER_SESSION] = "MAINTAINED"
    asyncio.run(controller.refresh_from_backend())
    assert controller.callcenter_resolution == "MAINTAINED"

    asyncio.run(controller.handle_qr(f'{{"session_id": "{SAFE_SESSION}"}}'))
    assert controller.callcenter_resolution is None
    assert controller.snapshot()["state"] == STATE_WITHDRAW_ENABLED


# ── 디바이스 키 설정 오류 (장애로 위장되면 안 된다) ─────────────────────────
def test_auth_failure_never_falls_back_to_qr_claim(
    controller: AtmController, backend: FakeBackend, provider: MockDeviceProvider
) -> None:
    """키가 틀렸을 때 QR이 스스로 적어 온 위험 등급을 믿으면 안 된다.

    이게 이 프로젝트에서 가장 위험한 조합이다 — `.env`의 DEVICE_API_KEY 오타 하나로
    ATM이 '오프라인 모드'가 되어, 위조 QR이 SAFE라고 주장하면 서버가 DANGER로
    판정한 세션에서도 현금이 나가 버린다.
    """
    backend.auth_rejected = True
    forged = f'{{"session_id": "{DANGER_SESSION}", "risk_level": "SAFE"}}'

    snapshot = asyncio.run(controller.handle_qr(forged))

    assert snapshot["state"] == STATE_READY, "거래를 열어 주면 안 된다"
    assert snapshot["session_id"] is None
    assert snapshot["offline"] is False, "서버는 대답했다 — 오프라인이라고 하면 안 된다"
    assert snapshot["last_error"]

    asyncio.run(controller.request_withdraw(500000))
    assert provider.dispense_count == 0


def test_auth_failure_shows_actionable_message_not_jargon(
    controller: AtmController, backend: FakeBackend
) -> None:
    """화면에는 원인 대신 무엇을 해야 하는지가 떠야 한다 (FR-10 노약자 안내)."""
    backend.auth_rejected = True
    snapshot = asyncio.run(controller.handle_qr(f'{{"session_id": "{SAFE_SESSION}"}}'))

    message = snapshot["last_error"] or ""
    assert "은행 직원" in message
    assert "DEVICE_API_KEY" not in message, "키 이름을 어르신 화면에 띄우지 않는다"


def test_auth_failure_during_polling_keeps_block_and_is_not_offline(
    controller: AtmController, backend: FakeBackend
) -> None:
    """폴링이 401을 받아도 제한은 유지하고, '오프라인'이라고 표시하지 않는다."""
    asyncio.run(controller.handle_qr(f'{{"session_id": "{DANGER_SESSION}"}}'))
    assert controller.state == STATE_WITHDRAW_BLOCKED

    backend.auth_rejected = True
    snapshot = asyncio.run(controller.refresh_from_backend())

    assert snapshot["state"] == STATE_WITHDRAW_BLOCKED
    assert snapshot["offline"] is False
    assert snapshot["last_error"]


def test_unexpected_backend_error_does_not_open_withdrawal(
    controller: AtmController, backend: FakeBackend, provider: MockDeviceProvider
) -> None:
    """원인을 모르는 오류에서도 QR 주장을 믿지 않는다 (서버에 닿았는지 모른다)."""

    def boom(_session_id: str) -> dict:
        raise ValueError("응답을 해석하지 못했습니다")

    backend.verify_session = boom  # type: ignore[method-assign]
    snapshot = asyncio.run(controller.handle_qr(
        f'{{"session_id": "{DANGER_SESSION}", "risk_level": "SAFE"}}'
    ))

    assert snapshot["state"] == STATE_READY
    asyncio.run(controller.request_withdraw(500000))
    assert provider.dispense_count == 0


def test_real_outage_still_uses_documented_backup_path(
    controller: AtmController, backend: FakeBackend, provider: MockDeviceProvider
) -> None:
    """서버에 정말 닿지 못하는 경우의 백업 경로는 그대로 살아 있어야 한다.

    docs/02 '백업 시연': 백엔드가 죽었을 때 risk_level이 든 QR로 차단까지는 시연한다.
    """
    backend.unavailable = True
    snapshot = asyncio.run(controller.handle_qr(
        f'{{"session_id": "{DANGER_SESSION}", "risk_level": "DANGER"}}'
    ))

    assert snapshot["offline"] is True
    assert snapshot["state"] == STATE_WITHDRAW_BLOCKED
    asyncio.run(controller.request_withdraw(500000))
    assert provider.dispense_count == 0


def test_auth_failure_tells_the_operator_how_to_fix_it(
    controller: AtmController, backend: FakeBackend
) -> None:
    """화면만 보고도 무엇을 고쳐야 하는지 알 수 있어야 한다.

    어르신용 안내에는 원인을 담지 않는다. 그런데 부스를 지키는 사람도 그 화면만
    보고 있어서, 원인을 알려면 데몬 터미널을 봐야 한다는 걸 모르면 한참 헤맨다.
    """
    backend.auth_rejected = True
    snapshot = asyncio.run(controller.handle_qr(f'{{"session_id": "{SAFE_SESSION}"}}'))

    hint = snapshot["operator_hint"] or ""
    assert "DEVICE_API_KEY" in hint
    assert "데몬" in hint, "고치고 나서 데몬을 다시 켜야 한다는 것까지 알려 준다"
    # 어르신용 문구에는 여전히 기술 용어가 없다
    assert "DEVICE_API_KEY" not in (snapshot["last_error"] or "")


def test_operator_hint_clears_once_it_works_again(
    controller: AtmController, backend: FakeBackend
) -> None:
    """설정을 고치면 단서도 사라진다 — 낡은 경고가 화면에 남으면 안 된다."""
    backend.auth_rejected = True
    asyncio.run(controller.handle_qr(f'{{"session_id": "{SAFE_SESSION}"}}'))
    assert controller.snapshot()["operator_hint"]

    backend.auth_rejected = False
    snapshot = asyncio.run(controller.handle_qr(f'{{"session_id": "{SAFE_SESSION}"}}'))
    assert snapshot["operator_hint"] is None
    assert snapshot["state"] == STATE_WITHDRAW_ENABLED


# ── ATM은 공용 기계다 (평상시 출금 가능) ─────────────────────────────────────
def test_atm_dispenses_before_anyone_shows_a_qr(
    controller: AtmController, provider: MockDeviceProvider
) -> None:
    """QR을 내밀지 않은 사람도 보통 ATM처럼 돈을 찾을 수 있어야 한다.

    지금 ATM 앞에 선 사람은 앱을 쓴 당사자일 수도, 가족일 수도, 이 시스템과
    아무 상관 없는 사람일 수도 있다. QR이 없다고 막으면 그건 ATM이 아니라
    QR 판독기다 — PRD의 "평범한 문자는 시스템이 건드리지 않는다"와도 어긋난다.
    """
    snapshot = controller.snapshot()
    assert snapshot["state"] == STATE_READY
    assert snapshot["can_withdraw"] is True
    assert "출금" in snapshot["guidance"]

    result = asyncio.run(controller.request_withdraw(50000))
    assert result["dispensed"] is True
    assert provider.dispense_count == 1


def test_danger_still_blocks_after_the_default_changed(
    controller: AtmController, provider: MockDeviceProvider
) -> None:
    """평상시를 열어 줬다고 해서 FR-09가 흔들리면 안 된다."""
    asyncio.run(controller.handle_qr(f'{{"session_id": "{DANGER_SESSION}"}}'))
    assert controller.snapshot()["can_withdraw"] is False

    for _ in range(3):
        assert asyncio.run(controller.request_withdraw(500000))["dispensed"] is False
    assert provider.dispense_count == 0


def test_unresolved_check_does_not_dispense(
    controller: AtmController, provider: MockDeviceProvider
) -> None:
    """확인을 요청했는데 확인하지 못했다면 내주지 않는다.

    '확인 못 함'은 '안전함'이 아니다. 등록되지 않은 QR을 내민 사람에게 그냥
    돈을 내주면, 보호 장치가 꺼진 것을 아무도 모른 채 지나간다.
    """
    asyncio.run(controller.handle_qr('{"session_id": "VP-999999"}'))
    assert controller.snapshot()["state"] == STATE_READY  # 상태는 평상시 그대로지만
    assert controller.snapshot()["can_withdraw"] is False  # 확인 실패가 남아 있다

    assert asyncio.run(controller.request_withdraw(50000))["dispensed"] is False
    assert provider.dispense_count == 0


def test_reset_returns_the_machine_to_the_next_customer(
    controller: AtmController, provider: MockDeviceProvider
) -> None:
    """'처음으로'를 누르면 다음 사람은 평범한 ATM을 만난다."""
    asyncio.run(controller.handle_qr('{"session_id": "VP-999999"}'))
    assert controller.snapshot()["can_withdraw"] is False

    controller.reset()
    assert controller.snapshot()["can_withdraw"] is True
    assert asyncio.run(controller.request_withdraw(50000))["dispensed"] is True
    assert provider.dispense_count == 1


# ── 다음 사람을 위한 자동 초기화 ─────────────────────────────────────────────
@pytest.fixture
def quick_reset(provider: MockDeviceProvider, backend: FakeBackend) -> AtmController:
    """자동 초기화를 아주 짧게 잡은 컨트롤러 (테스트가 1분을 기다릴 수는 없다)."""
    return AtmController(provider, backend, idle_reset_seconds=1)


def test_no_countdown_when_nothing_to_clear(quick_reset: AtmController) -> None:
    """아무 일도 없었던 평상시에는 셀 것이 없다 — 카운트다운도 뜨지 않는다."""
    assert quick_reset.snapshot()["idle_reset_in"] is None
    assert quick_reset.reset_if_idle() is False


def test_blocked_screen_hands_the_machine_to_the_next_person(
    quick_reset: AtmController, provider: MockDeviceProvider
) -> None:
    """앞사람이 남긴 차단 화면이 뒤에 온 사람에게 그대로 넘어가면 안 된다."""
    asyncio.run(quick_reset.handle_qr(f'{{"session_id": "{DANGER_SESSION}"}}'))
    assert quick_reset.snapshot()["idle_reset_in"] is not None  # 이제부터 센다

    time.sleep(1.05)
    assert quick_reset.reset_if_idle() is True

    snapshot = quick_reset.snapshot()
    assert snapshot["state"] == STATE_READY
    assert snapshot["session_id"] is None
    assert snapshot["can_withdraw"] is True, "다음 사람은 평범한 ATM을 만난다"


def test_waiting_for_the_call_center_is_not_idling(quick_reset: AtmController) -> None:
    """상담원을 기다리는 동안에는 세지 않는다.

    이건 노는 시간이 아니라 **사람을 기다리는** 시간이다. 여기서 시계를 돌리면
    확인이 오기도 전에 상담 자체가 사라지고, 시연 중에는 장면 5~6을 설명하는
    사이에 화면이 저절로 초기화된다.
    """
    asyncio.run(quick_reset.handle_qr(f'{{"session_id": "{DANGER_SESSION}"}}'))
    asyncio.run(quick_reset.enter_call_center())
    assert quick_reset.state == STATE_CALL_CENTER

    assert quick_reset.snapshot()["idle_reset_in"] is None
    time.sleep(1.05)
    assert quick_reset.reset_if_idle() is False, "기다리는 중에 치워 버리면 안 된다"
    assert quick_reset.state == STATE_CALL_CENTER


def test_countdown_restarts_after_the_agent_answers(
    quick_reset: AtmController, backend: FakeBackend
) -> None:
    """상담원이 답을 주면 기다림이 끝난다 — 그때부터 다시 센다."""
    asyncio.run(quick_reset.handle_qr(f'{{"session_id": "{DANGER_SESSION}"}}'))
    asyncio.run(quick_reset.enter_call_center())
    time.sleep(1.05)  # 기다리는 동안은 아무리 지나도 안 센다

    backend.status_action[DANGER_SESSION] = "ALLOW"
    asyncio.run(quick_reset.refresh_from_backend())

    remaining = quick_reset.snapshot()["idle_reset_in"]
    assert remaining is not None and remaining > 0, "답을 받은 순간부터 새로 센다"


def test_any_action_restarts_the_countdown(quick_reset: AtmController) -> None:
    """사람이 무언가를 하면 시계는 처음으로 돌아간다."""
    asyncio.run(quick_reset.handle_qr(f'{{"session_id": "{DANGER_SESSION}"}}'))
    time.sleep(0.7)
    asyncio.run(quick_reset.request_withdraw(50000))  # 출금 버튼도 '동작'이다
    time.sleep(0.7)
    assert quick_reset.reset_if_idle() is False, "누른 지 0.7초밖에 안 됐다"


def test_auto_reset_can_be_turned_off(
    provider: MockDeviceProvider, backend: FakeBackend
) -> None:
    """리허설에서 화면을 오래 띄워 두고 싶을 때는 0으로 끈다."""
    controller = AtmController(provider, backend, idle_reset_seconds=0)
    asyncio.run(controller.handle_qr(f'{{"session_id": "{DANGER_SESSION}"}}'))
    assert controller.snapshot()["idle_reset_in"] is None
    time.sleep(0.2)
    assert controller.reset_if_idle() is False
