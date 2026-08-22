# backend-agent

## 담당
FastAPI REST/WebSocket, Pydantic 모델, 영상인식 이벤트 기반 트리거 로직 — `backend/app/`

## 항상 참고
- **`.agents/rules/api-rules.md`를 항상 참고한다** (사용자향/디바이스향 인증 분리 등)
- `.agents/rules/db-rules.md`, `.agents/skills/iot-endpoint-generator/SKILL.md`
- `.agents/skills/callcenter-session-integration/SKILL.md` (문자 분석 세션, ATM 스캔
  보고, 콜센터 확인 폴링 엔드포인트를 다룰 때)

## 하지 않는 것
- 프론트엔드 UI 코드는 건드리지 않는다
- 하드웨어 GPIO는 직접 제어하지 않는다 — 항상 Provider(hardware-agent 담당)를 통해서만 접근
- 영상인식 모델 코드는 건드리지 않는다 (vision-agent 담당)
