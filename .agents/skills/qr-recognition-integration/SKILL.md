---
name: qr-recognition-integration
description: >-
  프론트엔드(Next.js)에서 위험 판정 결과를 QR 코드로 생성하고, 라즈베리파이 5(ATM)에서
  카메라로 QR을 인식·파싱해 로컬로 SAFE/DANGER를 판단할 때 사용하는 스킬.
---

# qr-recognition-integration

> "스마트 금융 보안 ATM"처럼 웹캠으로 사람/사물을 감지하는 게 아니라 **QR 코드를
> 인식**해야 할 때 이 스킬을 참고한다. `vision-recognition-integration`(YOLO·
> mediapipe)과는 다른 문제이므로 그 스킬을 그대로 적용하지 않는다.

## 어디서 도는 코드인가
QR 스캐너는 ATM 실물(라즈베리파이)에 물리적으로 붙어 있으므로, 최종 QR 인식 코드는
`vision/`이 아니라 **`pi/main.py`**에 들어간다. 개발 초반에는 Windows PC 웹캠으로
먼저 검증한 뒤 그대로 파이로 옮기는 것을 권장한다.

## QR 생성 (Frontend, Next.js)
백엔드 왕복 없이 브라우저에서 바로 생성한다.
```bash
npm install qrcode
npm install -D @types/qrcode
```
```tsx
import QRCode from "qrcode";

const qrDataUrl = await QRCode.toDataURL(JSON.stringify({
  session_id: sessionId,
  risk_level: "DANGER",
  detected_at: new Date().toISOString(),
  summary: "기관 사칭 및 현금 인출 요구 감지",
  token: "TEMP_TOKEN",
}));
// <img src={qrDataUrl} />
```

## QR 인식 (Raspberry Pi, pi/main.py)
새 시스템 라이브러리(zbar/pyzbar) 설치 없이, `opencv-python`의
`cv2.QRCodeDetector`만으로 디코딩한다(Windows/Pi 설치 부담을 늘리지 않기 위한 선택).
```bash
cd pi
pip install opencv-python requests python-dotenv gpiozero lgpio
```
```python
import cv2, json

detector = cv2.QRCodeDetector()
cap = cv2.VideoCapture(0)

while True:
    ok, frame = cap.read()
    if not ok:
        continue
    data, points, _ = detector.detectAndDecode(frame)
    if data:
        payload = json.loads(data)
        risk_level = payload["risk_level"]
        # SAFE/CAUTION -> WITHDRAW_ENABLED, DANGER -> WITHDRAW_BLOCKED
```

## 로컬 판단 원칙 (중요)
QR 안에 이미 `risk_level`이 들어있으므로, ATM은 **백엔드의 desired-state를 기다리지
않고 QR을 읽는 즉시 로컬에서 SAFE/DANGER를 판단**한다. `backend/iot/base.py`의
`DeviceProvider` 인터페이스(`set_actuator_state` 등)는 여전히 Mock↔실기기 전환에
쓰지만, 그것을 호출하는 주체가 원격 폴링 루프가 아니라 **같은 프로세스 안의 QR
파싱 로직**이라는 점이 킷의 기본 desired-state 폴링 패턴과 다르다. 인터넷 연결에
의존하지 않으려는 비기능 요구사항과도 맞는 방향이다.

QR 인식 후에는 `callcenter-session-integration` 스킬의 `POST /api/v1/atm/scan`으로
백엔드에 보고해 대시보드에 실시간 반영한다(선택 기능이지만 시연에 유용하다).

## QR 데이터 스키마
```json
{
  "session_id": "VP-001",
  "risk_level": "DANGER",
  "detected_at": "2026-08-20T15:30:00",
  "summary": "기관 사칭 및 현금 인출 요구 감지",
  "token": "TEMP_TOKEN"
}
```
`token`은 서버 검증(선택 기능)을 구현할 때만 사용한다.

## 예시 프롬프트
```
너는 이 프로젝트의 hardware-agent다. .agents/rules/hardware-rules.md와
.agents/skills/qr-recognition-integration/SKILL.md를 따른다.

pi/main.py에서 cv2.QRCodeDetector로 QR을 스캔해 로컬로 SAFE/DANGER를 판단하고
현금 배출 장치(HardwareDeviceProvider)를 바로 제어하는 로직을 만들어줘.
```
