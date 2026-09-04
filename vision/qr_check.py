"""PC 웹캠/이미지로 QR 인식만 먼저 검증하는 스크립트.

PRD 5.6 권장: ATM 전체 통합 전에 QR 인식을 독립적으로 먼저 검증한다.
여기서 잘 읽히는 것을 확인한 뒤 같은 코드를 pi/에서 쓴다.

사용법
  python vision/qr_check.py                # 웹캠으로 계속 스캔 (q 키로 종료)
  python vision/qr_check.py sample.png     # 이미지 파일 한 장 검사

설치
  pip install opencv-python
"""
import json
import sys

import cv2

WINDOW_NAME = "QR check (press q to quit)"


def check_image(path: str) -> int:
    """이미지 한 장에서 QR을 읽는다."""
    image = cv2.imread(path)
    if image is None:
        print(f"이미지를 열 수 없습니다: {path}")
        return 1

    data, _points, _straight = cv2.QRCodeDetector().detectAndDecode(image)
    if not data:
        print("QR을 찾지 못했습니다.")
        return 1

    print(f"읽은 내용: {data}")
    _print_session_id(data)
    return 0


def check_webcam(camera_index: int = 0) -> int:
    """웹캠으로 계속 스캔한다."""
    capture = cv2.VideoCapture(camera_index)
    if not capture.isOpened():
        print(f"카메라를 열 수 없습니다 (index={camera_index}).")
        return 1

    detector = cv2.QRCodeDetector()
    last = ""
    print("웹캠으로 QR을 비춰 보세요. 종료하려면 q 키를 누릅니다.")
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                continue

            data, _points, _straight = detector.detectAndDecode(frame)
            if data and data != last:
                last = data
                print(f"읽은 내용: {data}")
                _print_session_id(data)

            cv2.imshow(WINDOW_NAME, frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        capture.release()
        cv2.destroyAllWindows()
    return 0


def _print_session_id(data: str) -> None:
    """QR 규격(PRD 6.2)대로 session_id가 들어 있는지 알려준다."""
    try:
        payload = json.loads(data)
    except json.JSONDecodeError:
        print(f"  → JSON이 아닙니다. session_id 문자열로 해석하면: {data}")
        return

    session_id = payload.get("session_id") if isinstance(payload, dict) else None
    if session_id:
        print(f"  → session_id: {session_id}")
    else:
        print("  → session_id가 없습니다. 이 QR은 ATM 거래 제어에 쓸 수 없습니다.")


if __name__ == "__main__":
    sys.exit(check_image(sys.argv[1]) if len(sys.argv) > 1 else check_webcam())
