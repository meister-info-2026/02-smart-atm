"""DEVICE_MODE 값에 따라 Mock 또는 실기기 Provider를 돌려준다.

hardware-rules.md: 프론트엔드/백엔드 API 코드는 Mock인지 실기기인지 알지 못한다.
전환은 .env의 DEVICE_MODE 한 줄만 바꾼다.
"""
import logging
import os
from functools import lru_cache

from .base import DeviceProvider
from .mock_provider import MockDeviceProvider

logger = logging.getLogger("provider_factory")

MODE_MOCK = "mock"
MODE_HARDWARE = "hardware"


def create_provider(mode: str | None = None) -> DeviceProvider:
    """모드에 맞는 Provider 인스턴스를 만든다."""
    resolved = (mode or os.getenv("DEVICE_MODE", MODE_MOCK)).strip().lower()
    if resolved == MODE_HARDWARE:
        from .hardware_provider import HardwareDeviceProvider

        return HardwareDeviceProvider()
    if resolved != MODE_MOCK:
        logger.warning("알 수 없는 DEVICE_MODE=%s — mock으로 대체합니다.", resolved)
    return MockDeviceProvider()


@lru_cache(maxsize=1)
def get_provider() -> DeviceProvider:
    """프로세스 전역에서 하나만 쓰는 Provider."""
    return create_provider()
