-- ============================================================================
-- 스마트 금융 보안 ATM — MySQL 스키마 및 시드 데이터
--   PRD 5.9 주요 테이블 + .agents/rules/db-rules.md 최소 테이블
--
-- 이 파일은 자동 실행되지 않는다. 학생이 직접 MySQL에 실행한다:
--   mysql -u root -p < backend/db/init.sql
--
-- MySQL 전용 문법에는 `-- MySQL-only` 주석을 달아두었다
-- (db-migration 스킬이 Supabase 전환 시 이 주석을 기준으로 변환한다).
-- 날짜/시간은 전부 UTC로 저장한다 (db-rules.md).
-- ============================================================================

CREATE DATABASE IF NOT EXISTS smart_atm
  DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;  -- MySQL-only
USE smart_atm;

-- ── 사용자 / 친구 / 채팅 ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
  id            INT AUTO_INCREMENT PRIMARY KEY,                 -- MySQL-only
  username      VARCHAR(50)  NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,   -- Argon2 해시만 저장한다 (원문 저장 금지)
  display_name  VARCHAR(50)  NOT NULL,
  role          VARCHAR(20)  NOT NULL DEFAULT 'user',  -- 'user' | 'agent'(콜센터 상담원)
  created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS friendships (
  id             INT AUTO_INCREMENT PRIMARY KEY,                -- MySQL-only
  user_id        INT NOT NULL,
  friend_user_id INT NOT NULL,
  created_at     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_friendship (user_id, friend_user_id),
  FOREIGN KEY (user_id)        REFERENCES users(id),
  FOREIGN KEY (friend_user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS chat_rooms (
  id         INT AUTO_INCREMENT PRIMARY KEY,                    -- MySQL-only
  title      VARCHAR(100) NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS chat_room_members (
  id           INT AUTO_INCREMENT PRIMARY KEY,                  -- MySQL-only
  chat_room_id INT NOT NULL,
  user_id      INT NOT NULL,
  joined_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_chat_member (chat_room_id, user_id),
  FOREIGN KEY (chat_room_id) REFERENCES chat_rooms(id),
  FOREIGN KEY (user_id)      REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS messages (
  id             INT AUTO_INCREMENT PRIMARY KEY,                -- MySQL-only
  chat_room_id   INT NOT NULL,
  sender_user_id INT NULL,
  sender_label   VARCHAR(50) NOT NULL,
  content        TEXT NOT NULL,
  sent_at        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (chat_room_id)   REFERENCES chat_rooms(id),
  FOREIGN KEY (sender_user_id) REFERENCES users(id)
);

-- ── 분석 결과 / ATM 세션 ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS analysis_results (
  id           INT AUTO_INCREMENT PRIMARY KEY,                  -- MySQL-only
  user_id      INT NOT NULL,
  chat_room_id INT NULL,
  message_id   INT NULL,
  message_text TEXT NOT NULL,
  risk_level   VARCHAR(20) NOT NULL,   -- SAFE | CAUTION | DANGER
  risk_score   INT NOT NULL,           -- 0~100 (키워드 가중치 합, 100으로 상한)
  reasons      JSON NOT NULL,          -- 탐지 근거 문자열 배열
  summary      VARCHAR(255) NOT NULL DEFAULT '',
  engine       VARCHAR(20) NOT NULL DEFAULT 'rule',  -- rule | ai (추후 확장)
  detected_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id)      REFERENCES users(id),
  FOREIGN KEY (chat_room_id) REFERENCES chat_rooms(id),
  FOREIGN KEY (message_id)   REFERENCES messages(id)
);

-- QR에는 이 session_id만 들어간다 (PRD 6.2). 위험 상세는 서버에서 조회한다.
CREATE TABLE IF NOT EXISTS atm_sessions (
  id                    INT AUTO_INCREMENT PRIMARY KEY,         -- MySQL-only
  session_id            VARCHAR(50) NOT NULL UNIQUE,            -- 예: VP-000003
  analysis_id           INT NOT NULL,
  atm_status            VARCHAR(30) NOT NULL DEFAULT 'READY',
      -- READY | WITHDRAW_ENABLED | WITHDRAW_BLOCKED | CALL_CENTER
  callcenter_resolution VARCHAR(20) NULL,   -- NULL | MAINTAINED | RELEASED
  callcenter_note       VARCHAR(255) NULL,
  scanned_at            DATETIME NULL,
  resolved_at           DATETIME NULL,
  created_at            DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (analysis_id) REFERENCES analysis_results(id)
);

-- ── 장치 / 제어 이력 (db-rules.md 최소 테이블) ───────────────────────────────
-- 이 프로젝트에는 상시 폴링 센서가 없어 sensor_readings는 만들지 않는다 (PRD 5.5).
CREATE TABLE IF NOT EXISTS devices (
  id         VARCHAR(50) PRIMARY KEY,
  name       VARCHAR(100) NOT NULL,
  kind       VARCHAR(30)  NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS control_log (
  id         INT AUTO_INCREMENT PRIMARY KEY,                    -- MySQL-only
  device_id  VARCHAR(50) NOT NULL,
  action     VARCHAR(50) NOT NULL,
  value      VARCHAR(100) NULL,
  actor      VARCHAR(20) NOT NULL DEFAULT 'device',  -- 'user' 또는 'device'
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (device_id) REFERENCES devices(id)
);

-- ── 시드: AGENTS.md '팀 정보' 표의 제어 대상 ─────────────────────────────────
INSERT INTO devices (id, name, kind) VALUES
  ('cash_dispenser_1', '현금 배출 시연 장치 (MG996R x2)', 'cash_dispenser'),
  ('qr_scanner_1',     'QR 인식 카메라',                  'qr_scanner'),
  ('buzzer_1',         '경고 부저 (선택)',                'buzzer')
ON DUPLICATE KEY UPDATE name = VALUES(name), kind = VALUES(kind);  -- MySQL-only

-- 계정/채팅/문자 시드는 Argon2 해시가 필요하므로 SQL이 아니라 파이썬으로 만든다:
--   cd backend && python -m db.seed
