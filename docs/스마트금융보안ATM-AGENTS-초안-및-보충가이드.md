# 스마트 금융 보안 ATM — AGENTS.md 초안 및 보충 가이드

> **이 문서는 무엇인가요?**
> 「노약자를 위한 AI 문자 보이스피싱 예방 시스템(스마트 금융 보안 ATM)」팀의 PRD를
> 스타터 킷 구조와 대조 검토한 결과를 바탕으로 만든 문서입니다. 두 부분으로
> 구성됩니다.
> - **1부**: 이 팀 전용 `AGENTS.md` 초안 — 그대로 복사해 프로젝트 루트 `AGENTS.md`에
>   붙여넣고 `[미정]` 항목을 팀이 직접 채우면 됩니다.
> - **2부**: 스타터 킷의 기본 스킬(`vision-recognition-integration`은 YOLO·mediapipe
>   전제, `db-rules.md`의 최소 스키마 등)이 커버하지 않는, 이 팀만 추가로 설계해야
>   하는 부분 — QR 인식/생성, 콜센터 세션 폴링 엔드포인트, DB 스키마.
>
> PRD 작성 원칙과 동일하게, **PRD에 없는 내용은 임의로 만들어 넣지 않고 `[미정]`으로
> 남겨두었습니다.** 킷 적용 관점에서 권장하는 내용은 `[권장]`으로 표시합니다.

---

# 1부. AGENTS.md 초안 (팀 전용)

아래 블록 전체를 프로젝트 루트의 `AGENTS.md` 파일에 그대로 붙여넣고, `[미정]`만 팀이
채웁니다. `.agents/`, `docs/`는 이미 완성되어 있으므로 손대지 않습니다.

````markdown
# AGENTS.md — [프로젝트폴더명]

## 프로젝트 개요
- 팀 주제: `노약자를 위한 AI 문자 보이스피싱 예방 시스템 (스마트 금융 보안 ATM)`
- 한 줄 목표: `노약자가 받은 보이스피싱 의심 문자를 스마트폰/태블릿에서 분석하고,
  위험 결과를 QR로 라즈베리파이 기반 ATM에 전달하여 현금 인출을 제한한 뒤 콜센터
  확인으로 최종 대응하는 금융사기 예방 시스템을 구현한다`

## 기술 스택 (고정 — 임의로 바꾸지 않는다)
- 백엔드: FastAPI (Python)
- DB: MySQL (로컬 개발) → Supabase(PostgreSQL) (클라우드 배포 시 마이그레이션, 배포
  자체를 이 팀이 할지는 `[미정]` — 2부 참고)
- 프론트엔드: Next.js(TypeScript) — 스마트폰/태블릿 웹 화면 (네이티브 앱 아님)
- 하드웨어 제어: Python venv Mock(개발 전반부) → 라즈베리파이 5 + gpiozero(개발 후반부)
- 영상인식: **QR 코드 인식** (YOLO/mediapipe 아님) — Raspberry Pi 5 카메라 또는 QR
  스캐너, `qr-recognition-integration` 스킬 참고
- 배포: Render(백엔드) / Vercel(프론트) — 이 팀에 적용할지는 `[미정]`
- 버전관리: GitHub / 문서·협업: Notion

## 핵심 데이터 흐름

> 기본 스타터 킷 예시("웹캠이 사람/사물을 감지 → 즉시 액추에이터 제어")와 달리, 이
> 프로젝트는 **QR로 자기완결적 판정 결과를 전달**하고 **라즈베리파이가 백엔드의
> desired-state를 기다리지 않고 로컬에서 스스로 판단**합니다. 상세 설계는 2부를
> 참고합니다.

1. 사용자가 스마트폰/태블릿(Next.js)에서 의심 문자를 입력한다
2. 프론트엔드가 백엔드에 분석을 요청하면(`POST /api/analyze`), 백엔드가 규칙 기반
   (추후 AI로 확장 가능)으로 `risk_level`/`risk_score`/`reasons`와 `session_id`를
   반환하고 `analysis_sessions`에 기록한다
3. 위험(DANGER) 판정이면 프론트엔드가 응답을 그대로 QR로 변환해 화면에 표시한다
   (백엔드 왕복 없이 브라우저에서 바로 생성)
4. ATM(라즈베리파이)이 카메라로 QR을 스캔해 로컬에서 파싱하고, **desired-state를
   기다리지 않고 그 자리에서** SAFE/DANGER를 판단해 현금 배출 장치를 제어한다
5. ATM이 스캔 결과를 백엔드에 보고하면(`POST /api/v1/atm/scan`) WebSocket으로
   대시보드에 실시간 반영된다
6. DANGER면 ATM이 콜센터 확인 상태(`CALL_CENTER`)로 전환하고, desired-state
   폴링과 동일한 패턴으로 몇 초마다 해결 여부를 확인한다(또는 MVP에서는 ATM 화면의
   로컬 버튼으로 대체 — 2부 참고)
7. 콜센터가 정상 거래로 확인하면 제한을 해제하고, 보이스피싱으로 확인되면 제한을
   유지한다 — **경보성 디바이스 원칙(`db-rules.md`)과 동일하게, 시스템이 스스로
   풀지 않고 사람이 직접 확인해야 한다**

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
  시연이 가능해야 한다
- 이 프로젝트는 기본 스킬 범위를 넘는 부분(QR 인식/생성, 콜센터 세션 상태)이 있다 —
  해당 작업을 요청할 때는 `qr-recognition-integration`이나
  `callcenter-session-integration` 스킬, 또는 이 문서 2부의 절 번호를 함께 언급한다

## 폴더 구조
```
[프로젝트폴더명]/
├── AGENTS.md
├── .agents/            (하네스: rules/skills/workflows/hooks/agents — 이미 완성됨)
├── backend/            (FastAPI, .env.example 포함)
├── frontend/           (Next.js — 사용자용/ATM 디스플레이용/콜센터용 라우트를
│                         한 앱 안에서 분리, .env.example 포함)
├── vision/             (PC 웹캠으로 QR 인식을 먼저 검증할 때만 사용, 필수 아님)
└── pi/                 (라즈베리파이 — QR 인식과 현금 배출 장치 제어가 모두 여기서
                          돈다, 3주차부터, .env.example 포함)
```
각 폴더의 `.env.example`을 `.env`로 복사해 실제 값을 채운다 (`.env`는 커밋되지
않는다 — docs/스마트금융보안ATM-실행-가이드.md 1장 참고).

## 팀 정보

| 항목 | 값 |
|---|---|
| 팀 주제 | 노약자를 위한 AI 문자 보이스피싱 예방 시스템 (스마트 금융 보안 ATM) |
| 액추에이터(제어 대상) 목록 | 현금 배출 시연 장치(서보모터/모터, 구체 종류 `[미정]`), 부저/스피커(선택) |
| 센서(모니터링 대상) 목록 | 없음 — QR 인식 장치(카메라/스캐너, 구체 장치 `[미정]`)는 `devices` 테이블의 일반 센서 폴링 대상이 아니라 세션 단위로 처리한다(아래 "영상인식 감지 대상" 및 `callcenter-session-integration` 스킬 참고) |
| 영상인식 감지 대상 | **QR 코드 인식** — 일반 객체·얼굴·사람 감지 아님. `qr-recognition-integration` 스킬 참고 |
| 트리거 규칙 | QR 파싱 결과 기반 **로컬** 판단(SAFE/CAUTION→출금 가능, DANGER→출금 차단) + 콜센터 확인 후 최종 해제/유지. `CAUTION`일 때 ATM 동작 정책은 `[미정]`(PRD도 미정 — MVP는 SAFE/DANGER만 우선 검증) |
| 팀원 역할 분담 | `[미정]` (계획서 기준 5인 — 팀장/시스템통합, 모바일앱, AI/백엔드, ATM/하드웨어, 콜센터·UX·테스트. 앞의 3명은 각각 frontend-agent/backend-agent/hardware-agent와 대략 대응하고, "팀장·통합"과 "콜센터·UX·테스트"는 특정 AI 에이전트 하나에 대응하지 않는 조율·QA 역할이다. 실제 이름은 팀이 채운다) |
````

---

# 2부. 이 팀에 필요한 보충 설계

> 아래 내용은 스타터 킷의 기본 스킬(`vision-recognition-integration`은 YOLO·
> mediapipe 전제, `iot-endpoint-generator`는 디바이스 CRUD 전제)이 다루지 않는
> 것들입니다. 해당 작업을 backend-agent/hardware-agent/frontend-agent에게 요청할 때
> 이 절 번호를 프롬프트에 함께 적어주면 AI가 맥락을 정확히 참고합니다.

## 2-1. QR 인식은 `vision/`이 아니라 `pi/`에서 돕니다

킷의 기본 가정은 "영상인식은 Windows PC 웹캠, 하드웨어 제어는 라즈베리파이"로
분리되어 있지만(`vision-rules.md`), 이 프로젝트의 QR 스캐너는 ATM 실물(라즈베리파이)에
물리적으로 붙어 있어야 합니다. 즉 **최종 QR 인식 코드는 `pi/main.py`에 들어갑니다.**
개발 초반에는 Windows PC 웹캠으로 먼저 검증해도 되지만(`vision/`에 임시 스크립트로
두거나 그냥 로컬에서 테스트), 그대로 파이로 옮겨야 한다는 걸 팀이 처음부터 알고
있어야 합니다.

### QR 생성 (Frontend, Next.js)
백엔드 왕복 없이 브라우저에서 바로 생성합니다.
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

### QR 인식 (Raspberry Pi, pi/main.py) `[권장]`
새 시스템 라이브러리(zbar/pyzbar) 없이, 이미 킷에 포함된 `opencv-python`의
`cv2.QRCodeDetector`만으로 디코딩하는 것을 권장합니다(Windows/Pi 설치 부담을 늘리지
않기 위함).
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

### 로컬 판단 원칙 (중요)
QR 안에 이미 `risk_level`이 들어있으므로, ATM은 **백엔드의 desired-state를 기다리지
않고 QR을 읽는 즉시 로컬에서 SAFE/DANGER를 판단**합니다. `HardwareDeviceProvider.
set_actuator_state()`를 호출하는 주체가 원격 폴링 루프가 아니라 같은 프로세스 안의
QR 파싱 로직이라는 점이 킷의 기본 패턴과 다릅니다. 인터넷 연결에 의존하지 않기
위한 PRD의 비기능 요구사항과도 일치합니다. 판단 직후에는 결과를 아래 2-2의
`POST /api/v1/atm/scan`으로 백엔드에 보고해 대시보드에 실시간 반영합니다(선택
기능이지만 시연에 유용합니다).

### QR 데이터 스키마 (PRD 6.2 기준)
```json
{
  "session_id": "VP-001",
  "risk_level": "DANGER",
  "detected_at": "2026-08-20T15:30:00",
  "summary": "기관 사칭 및 현금 인출 요구 감지",
  "token": "TEMP_TOKEN"
}
```
`token`은 서버 검증(선택 기능, OF-03)을 구현할 때만 사용합니다.

## 2-2. 콜센터 세션 상태 폴링

### 문제
"콜센터 확인 결과를 ATM에 어떻게 전달할지"는 PRD도 `[미정]`으로 남겨뒀습니다. 이건
1번째 팀(기상 유도 알람 시스템)에게 만들어 준 desired-state 폴링 패턴을 그대로
재사용할 수 있는 지점입니다.

### 문자 분석 엔드포인트 (PRD 5.8 권장 형태)
```
POST /api/analyze
{"message": "검찰입니다. 계좌가 범죄에 연루되었습니다..."}

→ {
  "session_id": "VP-001",
  "risk_level": "DANGER",
  "risk_score": 92,
  "reasons": ["기관 사칭 표현 감지", "현금 인출 요구 감지"]
}
```
백엔드가 `session_id`를 생성해 함께 반환하고 `analysis_sessions`에 한 행을 만듭니다.
프론트엔드는 이 응답 전체를 그대로 QR에 넣습니다(2-1 참고).

### ATM 스캔 보고 (디바이스 인증)
**`POST /api/v1/atm/scan`** (헤더: `X-Device-Api-Key`)
```json
{ "session_id": "VP-001", "atm_status": "WITHDRAW_BLOCKED" }
```
`analysis_sessions.atm_status`, `scanned_at`을 갱신하고 WebSocket으로 대시보드에
브로드캐스트합니다.

### 콜센터 확인 폴링 (디바이스 인증)
`WITHDRAW_BLOCKED` 상태에서 콜센터 확인이 필요하면, desired-state 폴링과 동일한
패턴으로 ATM이 몇 초마다 해결 여부를 확인합니다.

**`GET /api/v1/atm/session-status/{session_id}`** (헤더: `X-Device-Api-Key`)
```json
{
  "data": {
    "atm_status": "CALL_CENTER",
    "callcenter_resolution": null
  }
}
```
상담원이 확인을 마치면 `atm_status`가 `WITHDRAW_ENABLED`(해제) 또는 그대로
`WITHDRAW_BLOCKED`(유지)로 바뀌어 응답에 반영됩니다.

### 콜센터 확인 처리 (별도 상담원 화면을 만들 경우 — 선택 기능)
**`POST /api/v1/callcenter/resolve/{session_id}`**
```json
{ "resolution": "RELEASED" }
```
`resolution`은 `"RELEASED"` 또는 `"MAINTAINED"`입니다. `callcenter_resolution`,
`atm_status`, `resolved_at`을 갱신합니다. 인증 방식(사용자 JWT 재사용 여부 등)은
`[미정]` — 별도 상담원 화면 자체가 PRD상 선택 기능이므로, MVP는 인증 없이 갈지
팀이 정합니다.

### 경보성 디바이스 원칙 재확인
`db-rules.md`의 경보성 디바이스 원칙과 동일하게, `WITHDRAW_BLOCKED` 상태는 시스템이
스스로 풀지 않습니다. 사람(콜센터)이 명시적으로 `RELEASED`를 기록해야만 해제됩니다.

### MVP 대안 (네트워크 없이) `[권장]`
별도 상담원 웹 화면은 PRD상 선택 기능입니다(8.4). 네트워크 연동 없이 먼저
시연하려면, ATM 화면 자체에 "상담원 확인 완료(관리자용)" 버튼을 두고 로컬에서 바로
`WITHDRAW_ENABLED`로 전환하는 방식으로 시작해도 FR-11(콜센터 확인 흐름)을 만족합니다
— 이후 위 엔드포인트로 확장하면 됩니다.

## 2-3. DB 스키마

`db-rules.md`의 최소 4테이블 중 `devices`/`control_log`는 QR 스캐너·현금 배출
장치를 등록하는 용도로 그대로 쓰되, **`sensor_readings`는 이 프로젝트에 상시
모니터링 센서가 없어 사실상 사용하지 않습니다**(PRD 5.5: "계획서에 별도 환경 센서는
정의되어 있지 않다"). 대신 아래 테이블을 추가합니다.

```sql
CREATE TABLE IF NOT EXISTS analysis_sessions (
  id INT AUTO_INCREMENT PRIMARY KEY,
  session_id VARCHAR(50) NOT NULL UNIQUE,
  message TEXT NULL,
  risk_level VARCHAR(20) NOT NULL,                    -- SAFE | CAUTION | DANGER
  risk_score INT NULL,
  reasons JSON NULL,
  atm_status VARCHAR(30) DEFAULT 'WITHDRAW_ENABLED',  -- WITHDRAW_ENABLED | WITHDRAW_BLOCKED | CALL_CENTER
  callcenter_resolution VARCHAR(20) NULL,             -- NULL | MAINTAINED | RELEASED
  scanned_at DATETIME NULL,
  resolved_at DATETIME NULL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

DB 저장 자체가 PRD상 선택 기능(거래 이력/탐지 기록)과 연결되지만, `session_id`
단위 최소 저장은 콜센터 확인 흐름(2-2)이 동작하려면 사실상 필수입니다 — PRD도 같은
구조를 권장합니다("최소한 analysis_session 단위로 세션 ID, 위험 등급, 탐지 시각,
상태를 저장하는 구조를 검토").

## 2-4. AI 프롬프트 예시

**DB + 세션 엔드포인트 (db-agent → backend-agent)**
```
너는 이 프로젝트의 db-agent다. .agents/skills/db-integration/SKILL.md와
.agents/skills/callcenter-session-integration/SKILL.md를 따른다.

db-rules.md의 devices/control_log 테이블에 QR 인식 장치와 현금 배출 장치를 등록하고,
callcenter-session-integration 스킬의 analysis_sessions 테이블을 만들어줘.
```
```
너는 이 프로젝트의 backend-agent다. .agents/skills/callcenter-session-integration/SKILL.md를
따른다.

POST /api/analyze(규칙 기반 키워드 판별), POST /api/v1/atm/scan,
GET /api/v1/atm/session-status/{session_id}를 만들어줘.
```

**QR 인식/제어 (hardware-agent)**
```
너는 이 프로젝트의 hardware-agent다. .agents/rules/hardware-rules.md와
.agents/skills/qr-recognition-integration/SKILL.md를 따른다.

backend/iot/base.py의 DeviceProvider 인터페이스를 따르는 HardwareDeviceProvider로
현금 배출 장치를 제어하고, pi/main.py에서 QR을 스캔해 로컬로 SAFE/DANGER를 판단해
바로 반영하는 로직을 만들어줘.
```

**QR 생성 (frontend-agent)**
```
너는 이 프로젝트의 frontend-agent다. .agents/skills/qr-recognition-integration/SKILL.md를
따른다.

분석 결과가 DANGER일 때 QR 데이터를 생성해 화면에 표시하는 컴포넌트를 만들어줘.
```

---

# 3부. 참고

- 이 문서는 팀의 「프로젝트 개발 계획서」/PRD(스마트 금융 보안 ATM) 검토를 바탕으로
  작성되었습니다. PRD에 없는 내용은 임의로 만들지 않고 `[미정]`으로 남겼습니다 —
  실제 값은 팀이 채웁니다.
- `docs/백엔드-라즈베리파이5-연동-인터페이스-가이드.md` — desired-state 폴링 계약
  (2-2절의 세션 상태 폴링이 동일한 패턴을 따릅니다)
- `.agents/rules/vision-rules.md` — 개인정보 보호 원칙(문자 원문·개인정보를
  불필요하게 저장하지 않는 것은 이 프로젝트에도 그대로 적용됩니다)
- `.agents/rules/db-rules.md` — 경보성 디바이스 원칙, 최소 스키마
- `.agents/rules/api-rules.md` — 사용자향/디바이스향 인증 분리
- `docs/윈도우-개발-핸드북.md`
