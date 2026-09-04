"""QR 인식 — opencv-python의 cv2.QRCodeDetector만 사용한다.

qr-recognition-integration 스킬: zbar/pyzbar 같은 별도 시스템 라이브러리를 설치하지
않아도 되도록 OpenCV 내장 디텍터를 쓴다 (Windows/라즈베리파이 설치 부담 최소화).

카메라 없이도 동작을 검증할 수 있게 정지 이미지 디코딩 함수를 함께 둔다
(PRD 5.6 권장: 먼저 정지 이미지/웹캠으로 검증한 뒤 ATM UI와 통합한다).
"""
import logging
import time
from collections.abc import Callable

logger = logging.getLogger("qr_scanner")

# 같은 QR을 연속으로 읽어 중복 처리하지 않도록 두는 최소 간격
SAME_CODE_COOLDOWN_SECONDS = 3.0
FRAME_INTERVAL_SECONDS = 0.1


def decode_image_file(path: str) -> str | None:
    """이미지 파일 한 장에서 QR 문자열을 읽는다. 없으면 None."""
    import cv2

    image = cv2.imread(path)
    if image is None:
        raise FileNotFoundError(f"이미지를 열 수 없습니다: {path}")
    data, _points, _straight = cv2.QRCodeDetector().detectAndDecode(image)
    return data or None


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

    capture = cv2.VideoCapture(camera_index)
    if not capture.isOpened():
        raise RuntimeError(f"카메라를 열 수 없습니다 (index={camera_index}).")

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
