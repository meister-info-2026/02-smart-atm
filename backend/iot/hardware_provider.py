"""라즈베리파이 5 하드웨어 Provider — gpiozero로 MG996R 서보를 제어한다.

hardware-rules.md:
- gpiozero를 우선 사용한다
- Mock과 동일한 DeviceProvider 인터페이스를 구현한다 (전환은 DEVICE_MODE만 바꾼다)

PRD 5.4: 실제 GPIO 핀 번호는 조립 단계에서 확정한다 → .env로 분리해 두고,
확정되면 값만 채운다. MG996R은 별도 5V 전원을 쓰고 파이는 신호만 준다.
"""
import asyncio
import logging
import os
from typing import Any, Optional

from .base import DeviceProvider
from .mock_provider import DISPENSER_DISPENSING, DISPENSER_IDLE

logger = logging.getLogger("hardware_provider")

# 서보 각도 (조립 후 실측으로 조정한다)
SERVO_CLOSED_ANGLE = 0
SERVO_OPEN_ANGLE = 90
DISPENSE_HOLD_SECONDS = 1.0


class HardwareDeviceProvider(DeviceProvider):
    """gpiozero 기반 실기기 제어. import 실패 시 즉시 원인을 알린다."""

    def __init__(self) -> None:
        try:
            from gpiozero import AngularServo, Buzzer
        except ImportError as exc:  # 예외를 조용히 삼키지 않는다
            raise RuntimeError(
                "gpiozero를 불러오지 못했습니다. 라즈베리파이 5에서 "
                "'pip install gpiozero lgpio' 후 GPIOZERO_PIN_FACTORY=lgpio 로 실행하세요."
            ) from exc

        gate_pin = int(os.getenv("SERVO_GATE_PIN", "18"))
        pusher_pin = int(os.getenv("SERVO_PUSHER_PIN", "19"))
        buzzer_pin = os.getenv("BUZZER_PIN", "").strip()

        # MG996R 2개: 배출구 게이트 + 지폐 밀대
        self._gate = AngularServo(gate_pin, min_angle=0, max_angle=180)
        self._pusher = AngularServo(pusher_pin, min_angle=0, max_angle=180)
        self._buzzer = Buzzer(int(buzzer_pin)) if buzzer_pin else None

        self._gate.angle = SERVO_CLOSED_ANGLE
        self._pusher.angle = SERVO_CLOSED_ANGLE
        self._dispenser_state = DISPENSER_IDLE
        self._buzzer_state = "OFF"
        self.dispense_count = 0

        logger.info("하드웨어 Provider 시작 (gate=GPIO%d, pusher=GPIO%d)", gate_pin, pusher_pin)

    async def _dispense_once(self) -> None:
        """게이트를 열고 밀대를 밀었다가 원위치시킨다."""
        self._gate.angle = SERVO_OPEN_ANGLE
        self._pusher.angle = SERVO_OPEN_ANGLE
        await asyncio.sleep(DISPENSE_HOLD_SECONDS)
        self._pusher.angle = SERVO_CLOSED_ANGLE
        self._gate.angle = SERVO_CLOSED_ANGLE
        self.dispense_count += 1

    async def get_device_status(self, device_id: str) -> Optional[dict[str, Any]]:
        states = {
            "cash_dispenser_1": self._dispenser_state,
            "buzzer_1": self._buzzer_state,
            "qr_scanner_1": "READY",
        }
        if device_id not in states:
            return None
        return {"device_id": device_id, "state": states[device_id]}

    async def set_actuator_state(
        self,
        device_id: str,
        desired_state: str,
        value: Optional[Any] = None,
        operator: str = "user",
    ) -> dict[str, Any]:
        if device_id == "cash_dispenser_1":
            if desired_state == DISPENSER_DISPENSING:
                await self._dispense_once()
            self._dispenser_state = DISPENSER_IDLE
            return {"device_id": device_id, "state": self._dispenser_state}

        if device_id == "buzzer_1":
            if self._buzzer is None:
                logger.warning("BUZZER_PIN이 설정되지 않아 부저 명령을 무시합니다.")
            elif desired_state == "ON":
                self._buzzer.on()
            else:
                self._buzzer.off()
            self._buzzer_state = desired_state
            return {"device_id": device_id, "state": self._buzzer_state}

        raise KeyError(f"제어할 수 없는 디바이스입니다: {device_id}")

    async def read_sensor_value(self, device_id: str) -> dict[str, Any]:
        return {"device_id": device_id, "value": None, "unit": None}

    async def get_all_statuses(self) -> list[dict[str, Any]]:
        return [
            {"device_id": "cash_dispenser_1", "state": self._dispenser_state},
            {"device_id": "buzzer_1", "state": self._buzzer_state},
            {"device_id": "qr_scanner_1", "state": "READY"},
        ]
