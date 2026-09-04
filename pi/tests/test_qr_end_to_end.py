"""실제 QR 이미지를 만들어 읽는 종단 검증.

PRD 5.6 권장: ATM 전체 통합 전에 정지 이미지/웹캠 QR 인식을 먼저 검증한다.
opencv/qrcode가 없는 환경에서는 자동으로 건너뛴다.
"""
import asyncio
import json
from pathlib import Path

import pytest

from atm_controller import STATE_WITHDRAW_BLOCKED, STATE_WITHDRAW_ENABLED, AtmController
from iot.mock_provider import MockDeviceProvider

cv2 = pytest.importorskip("cv2", reason="opencv-python이 설치되어 있지 않습니다.")
qrcode = pytest.importorskip("qrcode", reason="qrcode가 설치되어 있지 않습니다.")

from qr_scanner import decode_image_file  # noqa: E402

from fakes import DANGER_SESSION, SAFE_SESSION, FakeBackend  # noqa: E402


def _write_qr(payload: dict, path: Path) -> Path:
    """프론트엔드가 만드는 것과 같은 JSON을 QR 이미지로 저장한다."""
    image = qrcode.make(json.dumps(payload, ensure_ascii=False))
    image.save(path)
    return path


def test_qr_image_roundtrip_blocks_cash_for_danger(tmp_path: Path) -> None:
    """DANGER 세션 QR 이미지를 실제로 디코딩해도 현금이 배출되지 않는다."""
    qr_path = _write_qr({"session_id": DANGER_SESSION}, tmp_path / "danger.png")

    decoded = decode_image_file(str(qr_path))
    assert decoded is not None
    assert json.loads(decoded)["session_id"] == DANGER_SESSION

    provider = MockDeviceProvider()
    controller = AtmController(provider, FakeBackend())
    snapshot = asyncio.run(controller.handle_qr(decoded))

    assert snapshot["state"] == STATE_WITHDRAW_BLOCKED
    asyncio.run(controller.request_withdraw(50000))
    assert provider.dispense_count == 0


def test_qr_image_roundtrip_allows_cash_for_safe(tmp_path: Path) -> None:
    """SAFE 세션 QR 이미지는 정상적으로 출금이 열린다."""
    qr_path = _write_qr({"session_id": SAFE_SESSION}, tmp_path / "safe.png")
    decoded = decode_image_file(str(qr_path))

    provider = MockDeviceProvider()
    controller = AtmController(provider, FakeBackend())
    snapshot = asyncio.run(controller.handle_qr(decoded))

    assert snapshot["state"] == STATE_WITHDRAW_ENABLED
    asyncio.run(controller.request_withdraw(50000))
    assert provider.dispense_count == 1
