# AGENTS.md — 스마트-금융-보안-ATM

## 프로젝트 개요
- 팀 주제: `노약자를 위한 AI 문자 보이스피싱 예방 시스템 (스마트 금융 보안 ATM)`
- 한 줄 목표: `노약자가 받은 보이스피싱 의심 문자를 스마트폰/태블릿에서 분석하고,
  위험 결과를 QR로 라즈베리파이 기반 ATM에 전달하여 현금 인출을 제한한 뒤 콜센터
  확인으로 최종 대응하는 금융사기 예방 시스템을 구현한다`

## 기술 스택 (고정 — 임의로 바꾸지 않는다)
- 백엔드: FastAPI (Python)
- DB: MySQL (로컬 개발) → Supabase(PostgreSQL) (클라우드 배포 시 마이그레이션, 배포
  자체를 이 팀이 할지는 `[미정]` — docs/스마트금융보안ATM-AGENTS-초안-및-보충가이드.md 참고)
- 프론트엔드: Next.js(TypeScript) — 스마트폰/태블릿 웹 화면 (네이티브 앱 아님)
- 하드웨어 제어: Python venv Mock(개발 전반부) → 라즈베리파이 5 + gpiozero(개발 후반부)
- 영상인식: **QR 코드 인식** (YOLO/mediapipe 아님) — Raspberry Pi 5 카메라 또는 QR
  스캐너, `qr-recognition-integration` 스킬 참고
- 배포: Render(백엔드) / Vercel(프론트) — 이 팀에 적용할지는 `[미정]`
- 버전관리: GitHub / 문서·협업: Notion

## 핵심 데이터 흐름

> 기본 스타터 킷 예시("웹캠이 사람/사물을 감지 → 즉시 액추에이터 제어")와 달리, 이
> 프로젝트는 **QR로 자기완결적 판정 결과를 전달**하고 **라즈베리파이가 백엔드의
> desired-state를 기다리지 않고 로컬에서 스스로 판단**한다. 상세 설계는
> `docs/스마트금융보안ATM-AGENTS-초안-및-보충가이드.md` 2부와
> `.agents/skills/qr-recognition-integration/SKILL.md`,
> `.agents/skills/callcenter-session-integration/SKILL.md`를 참고한다.

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
   로컬 버튼으로 대체)
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
  `callcenter-session-integration` 스킬, 또는
  `docs/스마트금융보안ATM-AGENTS-초안-및-보충가이드.md`의 절 번호를 함께 언급한다

## 폴더 구조
```
스마트-금융-보안-ATM/
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
않는다 — docs/학생용-설치-및-사용-매뉴얼.md 1단계 참고).

## 팀 정보 (아래 표를 채운다 — AI에게 시키지 않고 직접 채운다)

| 항목 | 값 |
|---|---|
| 팀 주제 | 노약자를 위한 AI 문자 보이스피싱 예방 시스템 (스마트 금융 보안 ATM) |
| 액추에이터(제어 대상) 목록 | 현금 배출 시연 장치(서보모터/모터, 구체 종류 `[미정]`), 부저/스피커(선택) |
| 센서(모니터링 대상) 목록 | 없음 — QR 인식 장치(카메라/스캐너, 구체 장치 `[미정]`)는 `devices` 테이블의 일반 센서 폴링 대상이 아니라 세션 단위로 처리한다(아래 "영상인식 감지 대상" 및 `callcenter-session-integration` 스킬 참고) |
| 영상인식 감지 대상 | **QR 코드 인식** — 일반 객체·얼굴·사람 감지 아님. `qr-recognition-integration` 스킬 참고 |
| 트리거 규칙 | QR 파싱 결과 기반 **로컬** 판단(SAFE/CAUTION→출금 가능, DANGER→출금 차단) + 콜센터 확인 후 최종 해제/유지. `CAUTION`일 때 ATM 동작 정책은 `[미정]`(MVP는 SAFE/DANGER만 우선 검증) |
| 팀원 역할 분담 | `[미정]` (계획서 기준 5인 — 팀장/시스템통합, 모바일앱, AI/백엔드, ATM/하드웨어, 콜센터·UX·테스트. 앞의 3명은 각각 frontend-agent/backend-agent/hardware-agent와 대략 대응하고, "팀장·통합"과 "콜센터·UX·테스트"는 특정 AI 에이전트에 대응하지 않는 조율·QA 역할이다. 실제 이름은 팀이 채운다) |
