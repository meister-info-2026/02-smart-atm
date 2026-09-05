"""카메라 백엔드 선택 로직 검증.

Windows에서 OpenCV 기본 백엔드(MSMF)가 웹캠을 못 여는 사례가 잦아 DSHOW를 먼저
시도한다. 실제 카메라 없이 검증할 수 있도록 cv2 상수만 흉내 낸 가짜 모듈을 쓴다.
"""
from types import SimpleNamespace

import pytest

from qr_scanner import CAMERA_BACKEND_ENV, _backend_candidates

# 실제 OpenCV 상수값 (cv2.CAP_*)
FAKE_CV2 = SimpleNamespace(CAP_ANY=0, CAP_V4L2=200, CAP_DSHOW=700, CAP_MSMF=1400)


@pytest.fixture(autouse=True)
def _clear_backend_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """테스트마다 CAMERA_BACKEND를 비워 실행 환경의 .env 영향을 없앤다."""
    monkeypatch.delenv(CAMERA_BACKEND_ENV, raising=False)


def test_windows_tries_dshow_first_then_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    """Windows에서는 dshow를 먼저 시도하고 기본값으로 되돌아간다."""
    monkeypatch.setattr("qr_scanner.sys.platform", "win32")

    assert _backend_candidates(FAKE_CV2) == [("dshow", 700), ("any", 0)]


def test_linux_keeps_opencv_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """라즈베리파이/리눅스는 기존 동작(기본 백엔드) 그대로 둔다."""
    monkeypatch.setattr("qr_scanner.sys.platform", "linux")

    assert _backend_candidates(FAKE_CV2) == [("any", 0)]


def test_env_forces_single_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    """CAMERA_BACKEND를 지정하면 그 백엔드 하나만 쓴다."""
    monkeypatch.setattr("qr_scanner.sys.platform", "win32")
    monkeypatch.setenv(CAMERA_BACKEND_ENV, "MSMF")  # 대소문자/공백은 무시한다

    assert _backend_candidates(FAKE_CV2) == [("msmf", 1400)]


def test_unknown_env_value_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """오타를 조용히 넘기지 않고 가능한 값을 알려 준다."""
    monkeypatch.setenv(CAMERA_BACKEND_ENV, "dshwo")

    with pytest.raises(ValueError, match="dshwo"):
        _backend_candidates(FAKE_CV2)
