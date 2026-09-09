# AGENTS.md — 스마트-금융-보안-ATM

## 프로젝트 개요
- 팀 주제: `노약자를 위한 AI 문자 보이스피싱 예방 시스템 (스마트 금융 보안 ATM)`
- 한 줄 목표: `노약자가 받은 보이스피싱 의심 문자를 스마트폰/태블릿에서 분석하고,
  위험 결과를 QR로 라즈베리파이 기반 ATM에 전달하여 현금 인출을 제한한 뒤 콜센터
  확인으로 최종 대응하는 금융사기 예방 시스템을 구현한다`
- 기준 문서: 팀 PRD(`스마트 금융 보안 ATM 실제 개발용 PRD`, 2026-09-04)

## 기술 스택 (고정 — 임의로 바꾸지 않는다)
- 백엔드: FastAPI (Python) + SQLAlchemy, `/api/v1` 구조 유지
- DB: MySQL (PRD 5.9 확정, 서버 내부 127.0.0.1에서만 접근)
  - 테스트/시연 백업으로 SQLite를 쓸 수 있다 (`DATABASE_URL`만 바꾼다)
  - Supabase(PostgreSQL) 전환은 `[미정]` — 하게 되면 `db-migration` 스킬 참고
- 프론트엔드: Next.js(TypeScript) — 스마트폰/태블릿 **웹** 화면
  - PRD '최종 구현환경'은 Flutter 네이티브 앱이지만, 이 저장소는 하네스 고정 스택인
    Next.js 웹으로 구현했다. 백엔드 API 계약(`docs/03_데이터-연동-규격.md`)은 그대로이므로
    Flutter로 갈아탈 때도 서버/ATM 쪽은 바꾸지 않아도 된다
  - 사용자용 / ATM 디스플레이용 / 콜센터용 라우트를 한 앱 안에서 분리한다
- 하드웨어 제어: Python venv Mock(개발 전반부) → 라즈베리파이 5 + gpiozero(개발 후반부)
- 영상인식: **QR 코드 인식** (YOLO/mediapipe 아님) — `cv2.QRCodeDetector`,
  `qr-recognition-integration` 스킬 참고
- 배포: Cafe24 Ubuntu VPS + systemd 상시 실행 (PRD 5.8). Render/Vercel은 `[미정]`
- 버전관리: GitHub / 문서·협업: Notion

## 핵심 데이터 흐름

> 기본 스타터 킷 예시("웹캠이 사람/사물을 감지 → 즉시 액추에이터 제어")와 달리, 이
> 프로젝트는 **QR로 세션 식별자만 전달**하고 **라즈베리파이가 백엔드의 desired-state를
> 기다리지 않고 QR을 읽는 즉시 스스로 판단**한다. 상세 설계는
> `docs/03_데이터-연동-규격.md`,
> `docs/부록C_스마트금융보안ATM-AGENTS-초안-및-보충가이드.md` 2부,
> `.agents/skills/qr-recognition-integration/SKILL.md`,
> `.agents/skills/callcenter-session-integration/SKILL.md`를 참고한다.

0. **ATM은 평상시 보통 ATM이다** — 아무 QR도 읽지 않은 상태에서 출금 화면이 떠 있고
   돈이 나온다. ATM 앞에 선 사람은 이 앱을 쓴 당사자일 수도, 가족일 수도, 시스템과
   아무 상관 없는 제삼자일 수도 있기 때문이다. 막는 대상은 '확인되지 않은 사람'이
   아니라 **'위험이 확인된 세션'**이다 (PRD: "평범한 문자는 시스템이 건드리지 않는다")
1. 사용자가 스마트폰/태블릿(Next.js `/messages`)에서 의심 문자를 고르거나 직접 입력한다
2. 프론트엔드가 백엔드에 분석을 요청하면(`POST /api/v1/analysis`), 백엔드가 규칙 기반
   (추후 AI로 확장 가능)으로 `risk_level`/`risk_score`/`reasons`를 만들고
   `analysis_results` + `atm_sessions`에 저장한 뒤 `session_id`와 함께 돌려준다
3. 위험(DANGER)·의심(CAUTION) 판정이면 프론트엔드가 **`session_id`만** QR로 만들어
   화면에 표시한다 (백엔드 왕복 없이 브라우저에서 바로 생성)
4. ATM(라즈베리파이)이 카메라로 QR을 스캔해 `session_id`를 꺼내고,
   `GET /api/v1/atm/verify/{session_id}`로 **서버 검증**해 ALLOW/VERIFY/BLOCK을 받는다
   (PRD 6.2 — 위험 상세와 개인정보를 QR에 넣지 않는다)
5. 로컬 판단으로 넘어가는 경우는 **서버에 닿지 못했을 때 하나뿐이다.** 그때 QR에
   `risk_level`이 함께 들어 있으면 그 값으로 시연을 이어간다. 서버가 401(디바이스 키
   거부)로 **대답을 한** 경우는 장애가 아니라 설정 오류이므로 로컬 판단으로 넘어가지
   않는다 — 서버가 대답했는데 QR이 스스로 적어 온 등급을 믿으면 그건 검증이 아니고,
   키 오타 하나로 위조 QR에 현금이 나간다. 확인하지 못한 경우에는 **거래를 열지 않고**
   오류를 안내한다 (`확인 못 함 ≠ 안전함`)
6. ATM이 스캔 결과를 보고하면(`POST /api/v1/atm/scan`) WebSocket으로 콜센터 화면에
   실시간 반영된다
7. DANGER면 ATM이 콜센터 확인 상태(`CALL_CENTER`)로 전환하고,
   `GET /api/v1/atm/session-status/{session_id}`를 몇 초마다 폴링한다
8. 콜센터가 정상 거래로 확인하면(`RELEASED`) 제한을 해제하고, 보이스피싱으로
   확인되면(`MAINTAINED`) 제한을 유지한다 — **경보성 디바이스 원칙(`db-rules.md`)과
   동일하게, 시스템이 스스로 풀지 않고 사람이 직접 확인해야 한다**
9. 조작이 1분간 없으면 ATM은 대기 화면으로 돌아간다(`IDLE_RESET_SECONDS`). 앞사람이
   남긴 차단 화면을 뒤에 온 사람이 물려받지 않게 하려는 것이며, **세션의 차단을 푸는
   것이 아니다** — 차단은 서버에 남아 있고 같은 QR을 다시 비추면 즉시 다시 막힌다.
   상담원 확인을 기다리는 동안(`CALL_CENTER`)에는 세지 않는다

## 확정된 판정 규칙 (PRD 5.2 / 9.3 — 임의로 바꾸지 않는다)

| 항목 | 값 |
|---|---|
| 위험 점수 | 키워드 범주별 가중치 합산 후 최대 100점 |
| 위험 등급 경계값 | 0~29 `SAFE` / 30~69 `CAUTION` / 70~100 `DANGER` |
| ATM 동작 | `SAFE`→`ALLOW`, `CAUTION`→`VERIFY`, `DANGER`→`BLOCK` |
| ATM 상태값 | `READY` / `WITHDRAW_ENABLED` / `WITHDRAW_BLOCKED` / `CALL_CENTER` |
| 콜센터 결과 | `RELEASED`(제한 해제) / `MAINTAINED`(제한 유지) |
| 분석 범주 7종 | 기관 사칭 · 범죄 연루 · 현금 인출 요구 · 송금 요구 · 긴급 행동 요구 · 비밀 유지 요구 · 특정 장소 현금 전달 |

## AI 사용 원칙
- 모든 작업은 `.agents/rules/karpathy-principles.md`의 4원칙(생각 먼저·단순함 우선·
  외과적 변경·목표 기반 실행)을 기본으로 따른다
- AI가 생성한 코드는 반드시 학생이 직접 실행하고 결과를 눈으로 확인한다
- "AI가 알아서 잘했다"는 요약만 믿고 다음 단계로 넘어가지 않는다
- 시크릿(API 키, 비밀번호)은 절대 채팅/프롬프트에 직접 입력하지 않는다 (security-rules.md 참고)
- 이 킷의 `.agents/rules`, `.agents/skills`는 이미 완성되어 있다 — **다시 만들어달라고
  요청하지 않는다.** 새 기능을 요청할 때 "역할 지정 + 관련 rules/skills 참고" 문구만
  붙이면 AI가 알아서 참고한다 (토큰 절약)
- 위험 분석은 **1단계 규칙 기반(키워드 매칭)으로 먼저 전체 흐름을 완성**하고, AI
  API/모델 연결은 그 다음이다(PRD 권장 순서). 외부 AI 연결이 실패해도 규칙 기반으로
  시연이 가능해야 한다 — `backend/analysis/`의 규칙 엔진은 백업 수단으로 계속 유지한다
- 이 프로젝트는 기본 스킬 범위를 넘는 부분(QR 인식/생성, 콜센터 세션 상태)이 있다 —
  해당 작업을 요청할 때는 `qr-recognition-integration`이나
  `callcenter-session-integration` 스킬, 또는 `docs/03_데이터-연동-규격.md`의 절 번호를
  함께 언급한다

## 폴더 구조
```
스마트-금융-보안-ATM/
├── README.md           (저장소 첫 화면 — 무엇이고 무엇이 되는가)
├── AGENTS.md
├── pytest.ini          (backend/pi 테스트를 한 번에 돌린다)
├── .agents/            (하네스: rules/skills/workflows/hooks/agents — 이미 완성됨)
├── backend/            (FastAPI)
│   ├── analysis/       규칙 기반 위험 판별 엔진
│   ├── db/             SQLAlchemy 모델 · init.sql · seed.py
│   ├── iot/            DeviceProvider (Mock ↔ 라즈베리파이 5)
│   ├── routers/        /api/v1 엔드포인트
│   ├── schemas/        Pydantic 요청·응답 모델
│   ├── security/       JWT(사용자향) · 디바이스 API 키(디바이스향)
│   └── tests/          규칙 엔진 · API 통합 테스트
├── frontend/           (Next.js)
│   ├── app/            / · /login · /messages · /result/[id] · /atm · /callcenter
│   │                   (app/atm/error.tsx — ATM 화면이 하얗게 비지 않게 하는 안전망)
│   ├── components/     RiskBadge · QrPanel · VoiceToggle 등
│   └── hooks/          useSpeech(음성 안내) · useAtmSocket(실시간)
├── vision/             (PC 웹캠으로 QR 인식을 먼저 검증할 때만 사용, 필수 아님)
├── pi/                 (라즈베리파이 — QR 인식 + 현금 배출 제어 + 로컬 화면 API)
└── scripts/            (demo_e2e.py — 통합 시연 자동 검증)
```
각 폴더의 `.env.example`을 `.env`로 복사해 실제 값을 채운다 (`.env`는 커밋되지
않는다 — `docs/02_스마트금융보안ATM-실행-가이드.md` 참고).

## 팀 정보

| 항목 | 값 |
|---|---|
| 팀 주제 | 노약자를 위한 AI 문자 보이스피싱 예방 시스템 (스마트 금융 보안 ATM) |
| 액추에이터(제어 대상) 목록 | 현금 배출 시연 장치 — TowerPro MG996R 서보모터 2개(`cash_dispenser_1`), 부저/스피커(`buzzer_1`, 선택) |
| 센서(모니터링 대상) 목록 | 없음 — QR 인식 카메라(`qr_scanner_1`)는 `devices`에 등록하되 상시 폴링 대상이 아니라 세션 단위로 처리한다. `sensor_readings` 테이블은 만들지 않는다 |
| 영상인식 감지 대상 | **QR 코드 인식** — 일반 객체·얼굴·사람 감지 아님. `qr-recognition-integration` 스킬 참고 |
| 트리거 규칙 | QR의 `session_id`를 서버에서 검증한 뒤 ATM이 **로컬**에서 판단 (`ALLOW`→출금 가능, `VERIFY`/`BLOCK`→출금 차단) + 콜센터 확인 후 최종 해제/유지. `CAUTION`은 `VERIFY`로 처리해 추가 확인 절차로 연결한다 |
| GPIO 핀맵 | `[미정]` — 조립 후 확정. 그때까지 `pi/.env`의 `SERVO_GATE_PIN`/`SERVO_PUSHER_PIN`/`BUZZER_PIN`으로만 바꾼다 (코드 수정 불필요) |
| 팀원 역할 분담 | `[미정]` (계획서 기준 5인 — 팀장/시스템통합, 모바일앱, AI/백엔드, ATM/하드웨어, 콜센터·UX·테스트. 앞의 3명은 각각 frontend-agent/backend-agent/hardware-agent와 대략 대응하고, "팀장·통합"과 "콜센터·UX·테스트"는 특정 AI 에이전트에 대응하지 않는 조율·QA 역할이다. 실제 이름은 팀이 채운다) |
