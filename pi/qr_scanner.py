"""QR 인식 — opencv-python의 cv2.QRCodeDetector만 사용한다.

qr-recognition-integration 스킬: zbar/pyzbar 같은 별도 시스템 라이브러리를 설치하지
않아도 되도록 OpenCV 내장 디텍터를 쓴다 (Windows/라즈베리파이 설치 부담 최소화).

카메라 없이도 동작을 검증할 수 있게 정지 이미지 디코딩 함수를 함께 둔다
(PRD 5.6 권장: 먼저 정지 이미지/웹캠으로 검증한 뒤 ATM UI와 통합한다).
"""
import logging
import os
import sys
import time
from collections.abc import Callable
from types import ModuleType
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # 런타임에는 cv2를 함수 안에서만 import한다 (설치 부담 최소화)
    import cv2

logger = logging.getLogger("qr_scanner")

# 같은 QR을 연속으로 읽어 중복 처리하지 않도록 두는 최소 간격
SAME_CODE_COOLDOWN_SECONDS = 3.0
FRAME_INTERVAL_SECONDS = 0.1

# 카메라 백엔드를 강제할 때 쓰는 환경변수 (.env의 CAMERA_BACKEND)
CAMERA_BACKEND_ENV = "CAMERA_BACKEND"
CAMERA_BACKEND_AUTO = "auto"


def decode_image_file(path: str) -> str | None:
    """이미지 파일 한 장에서 QR 문자열을 읽는다. 없으면 None."""
    import cv2

    image = cv2.imread(path)
    if image is None:
        raise FileNotFoundError(f"이미지를 열 수 없습니다: {path}")
    data, _points, _straight = cv2.QRCodeDetector().detectAndDecode(image)
    return data or None


def _backend_candidates(cv2_module: ModuleType) -> list[tuple[str, int]]:
    """열어 볼 OpenCV 카메라 백엔드를 순서대로 돌려준다.

    Windows 기본 백엔드(MSMF)는 웹캠을 여는 데 5~10초가 걸리거나 아무 메시지 없이
    실패하는 일이 잦다. 그래서 Windows에서는 DSHOW를 먼저 시도하고, 안 되면 OpenCV
    기본값으로 되돌아간다. 라즈베리파이/리눅스는 기본값이 잘 동작하므로 그대로 둔다.

    `.env`에 `CAMERA_BACKEND=dshow`처럼 적으면 그 백엔드 하나만 쓴다.
    """
    named: dict[str, int | None] = {
        "dshow": getattr(cv2_module, "CAP_DSHOW", None),
        "msmf": getattr(cv2_module, "CAP_MSMF", None),
        "v4l2": getattr(cv2_module, "CAP_V4L2", None),
        "any": cv2_module.CAP_ANY,
    }

    requested = os.getenv(CAMERA_BACKEND_ENV, CAMERA_BACKEND_AUTO).strip().lower()
    if requested and requested != CAMERA_BACKEND_AUTO:
        api = named.get(requested)
        if api is None:
            raise ValueError(
                f"{CAMERA_BACKEND_ENV}={requested} 는 이 환경에서 쓸 수 없는 값입니다. "
                f"가능한 값: {', '.join(named)}, {CAMERA_BACKEND_AUTO}"
            )
        return [(requested, api)]

    dshow = named["dshow"]
    if sys.platform == "win32" and dshow is not None:
        return [("dshow", dshow), ("any", cv2_module.CAP_ANY)]
    return [("any", cv2_module.CAP_ANY)]


def open_camera(camera_index: int = 0) -> "cv2.VideoCapture":
    """웹캠을 연다. 백엔드를 순서대로 시도하고 모두 실패하면 RuntimeError."""
    import cv2

    tried: list[str] = []
    for name, api in _backend_candidates(cv2):
        capture = cv2.VideoCapture(camera_index, api)
        if capture.isOpened():
            logger.info("카메라 열림 (index=%d, backend=%s)", camera_index, name)
            return capture
        capture.release()
        tried.append(name)

    raise RuntimeError(
        f"카메라를 열 수 없습니다 (index={camera_index}, 시도한 backend={', '.join(tried)}). "
        "Zoom·Teams·브라우저 등 웹캠을 쓰는 프로그램을 모두 끄고, USB 웹캠이면 "
        ".env의 CAMERA_INDEX를 1, 2로 바꿔 보세요."
    )


def scan_loop(
    on_qr: Callable[[str], None],
    camera_index: int = 0,
    stop_flag: Callable[[], bool] | None = None,
) -> None:
    """카메라를 열고 QR이 보일 때마다 on_qr(문자열)을 호출한다.

    별도 스레드에서 돌린다. 예외는 로그로 남기고 루프를 멈추지 않는다 —
    인식 실패로 ATM 전체가 죽으면 안 된다.
    """
    import cv2

    capture = open_camera(camera_index)
    detector = cv2.QRCodeDetector()
    last_data: str | None = None
    last_time = 0.0
    logger.info("QR 스캔 시작 (camera_index=%d)", camera_index)

    try:
        while not (stop_flag and stop_flag()):
            ok, frame = capture.read()
            if not ok:
                time.sleep(FRAME_INTERVAL_SECONDS)
                continue

            try:
                data, _points, _straight = detector.detectAndDecode(frame)
            except Exception as exc:  # noqa: BLE001
                logger.warning("QR 디코딩 오류(무시하고 계속): %s", exc)
                continue

            now = time.monotonic()
            if data and (data != last_data or now - last_time > SAME_CODE_COOLDOWN_SECONDS):
                last_data, last_time = data, now
                try:
                    on_qr(data)
                except Exception as exc:  # noqa: BLE001
                    logger.exception("QR 처리 중 오류: %s", exc)

            time.sleep(FRAME_INTERVAL_SECONDS)
    finally:
        capture.release()
        logger.info("QR 스캔 종료")
