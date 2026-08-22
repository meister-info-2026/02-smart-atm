---
name: callcenter-session-integration
description: >-
  문자 분석 세션(analysis_sessions) 저장, ATM 스캔 결과 보고, 콜센터 확인 후 제한
  유지/해제를 ATM에 전달하는 세션 상태 폴링 엔드포인트를 구현할 때 사용하는 스킬.
---

# callcenter-session-integration

> "콜센터 확인 후 ATM 제한을 유지하거나 해제"하는 흐름처럼, 사람의 최종 판단이
> 있어야 자동 판정이 뒤집힐 수 있는 경우 이 스킬을 참고한다. `iot-endpoint-generator`
> (디바이스 CRUD)와는 별개로, 세션 단위 상태 전이를 다룬다.

## DB 스키마
`db-rules.md`의 최소 4테이블은 그대로 두되, 이 프로젝트는 상시 센서가 없어
`sensor_readings`를 사실상 쓰지 않는다. 대신 아래 테이블을 추가한다.

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

## 문자 분석 엔드포인트
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
백엔드가 `session_id`를 생성해 함께 반환하고, `analysis_sessions`에 한 행을 만든다.
프론트엔드는 이 응답 전체를 그대로 QR에 넣는다(`qr-recognition-integration` 참고).
위험 판정은 1단계로 규칙 기반(키워드 매칭)부터 구현하고, AI API/모델은 그 다음
단계로 연결한다.

## ATM 스캔 보고 (디바이스 인증)
**`POST /api/v1/atm/scan`** (헤더: `X-Device-Api-Key`)
```json
{ "session_id": "VP-001", "atm_status": "WITHDRAW_BLOCKED" }
```
`analysis_sessions.atm_status`, `scanned_at`을 갱신하고 WebSocket으로 대시보드에
브로드캐스트한다.

## 콜센터 확인 폴링 (디바이스 인증)
`WITHDRAW_BLOCKED` 상태에서 콜센터 확인이 필요하면, desired-state 폴링과 동일한
패턴으로 ATM이 몇 초마다 해결 여부를 확인한다.

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
`WITHDRAW_BLOCKED`(유지)로 바뀌어 응답에 반영된다.

## 콜센터 확인 처리 (별도 상담원 화면을 만들 경우)
**`POST /api/v1/callcenter/resolve/{session_id}`**
```json
{ "resolution": "RELEASED" }
```
`resolution`은 `"RELEASED"` 또는 `"MAINTAINED"`다. `callcenter_resolution`,
`atm_status`, `resolved_at`을 갱신한다.

## 경보성 디바이스 원칙 재확인
`db-rules.md`의 경보성 디바이스 원칙과 동일하게, `WITHDRAW_BLOCKED` 상태는 시스템이
스스로 풀지 않는다. 사람(콜센터)이 명시적으로 `RELEASED`를 기록해야만 해제된다.

## MVP 대안 (네트워크 없이)
별도 상담원 웹 화면은 선택 기능이다. 네트워크 연동 없이 먼저 시연하려면, ATM 화면
자체에 "상담원 확인 완료(관리자용)" 버튼을 두고 로컬에서 바로 `WITHDRAW_ENABLED`로
전환하는 방식으로 시작해도 된다 — 이후 위 엔드포인트로 확장하면 된다.

## 예시 프롬프트
```
너는 이 프로젝트의 backend-agent다. .agents/rules/db-rules.md와
.agents/skills/callcenter-session-integration/SKILL.md를 따른다.

analysis_sessions 테이블, POST /api/analyze, POST /api/v1/atm/scan,
GET /api/v1/atm/session-status/{session_id}를 만들어줘.
```
