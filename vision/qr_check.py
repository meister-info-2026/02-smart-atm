"""PC 웹캠/이미지로 QR 인식만 먼저 검증하는 스크립트.

PRD 5.6 권장: ATM 전체 통합 전에 QR 인식을 독립적으로 먼저 검증한다.
여기서 잘 읽히는 것을 확인한 뒤 같은 코드를 pi/에서 쓴다.

사용법
  python vision/qr_check.py                # 웹캠으로 계속 스캔 (q 키로 종료)
  python vision/qr_check.py --camera 1     # 두 번째 카메라로 스캔 (USB 웹캠 등)
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


def _open_camera(camera_index: int) -> "cv2.VideoCapture | None":
    """웹캠을 연다. 못 열면 None.

    Windows 기본 백엔드(MSMF)는 웹캠을 여는 데 오래 걸리거나 아무 메시지 없이
    실패하는 일이 잦아, Windows에서는 DSHOW를 먼저 시도한다.
    pi/qr_scanner.py의 open_camera()와 같은 정책이다 — 이 스크립트는 opencv만
    설치하면 단독으로 돌아가야 해서 일부러 pi/를 import하지 않는다.
    """
    candidates: list[tuple[str, int]] = []
    if sys.platform == "win32" and hasattr(cv2, "CAP_DSHOW"):
        candidates.append(("dshow", cv2.CAP_DSHOW))
    candidates.append(("any", cv2.CAP_ANY))

    for name, api in candidates:
        capture = cv2.VideoCapture(camera_index, api)
        if capture.isOpened():
            print(f"카메라 열림 (index={camera_index}, backend={name})")
            return capture
        capture.release()
    return None


def check_webcam(camera_index: int = 0) -> int:
    """웹캠으로 계속 스캔한다."""
    capture = _open_camera(camera_index)
    if capture is None:
        print(f"카메라를 열 수 없습니다 (index={camera_index}).")
        print("Zoom·Teams·브라우저 등 웹캠을 쓰는 프로그램을 모두 끄고 다시 시도하세요.")
        print("USB 웹캠을 꽂았다면 --camera 1, --camera 2 로 바꿔 봅니다.")
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


def main(argv: list[str]) -> int:
    """인자에 따라 웹캠 스캔 또는 이미지 한 장 검사를 고른다."""
    if argv and argv[0] == "--camera":
        if len(argv) < 2 or not argv[1].isdigit():
            print("사용법: python vision/qr_check.py --camera <번호>")
            return 1
        return check_webcam(int(argv[1]))
    return check_image(argv[0]) if argv else check_webcam()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
