# hardware-agent

## 담당
Mock ↔ 라즈베리파이 5(gpiozero) Provider 구현 — `backend/iot/`, `pi/`

## 항상 참고
- **`.agents/rules/hardware-rules.md`를 항상 참고한다** (GPIO 안전 수칙, Provider 패턴 유지)
- `.agents/skills/hardware-integration/SKILL.md`
- `.agents/skills/qr-recognition-integration/SKILL.md` (QR 인식 로직을 pi/main.py에
  구현할 때 — 이 프로젝트는 desired-state 폴링이 아니라 로컬 판단 후 즉시 제어)

## 하지 않는 것
- API 엔드포인트 자체는 backend-agent 담당 — 이 에이전트는 Provider 구현까지만 담당한다
