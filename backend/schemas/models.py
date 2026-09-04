"""요청/응답 Pydantic 스키마 (api-rules.md 응답 형식의 data 안에 들어가는 부분)."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

RiskLevel = Literal["SAFE", "CAUTION", "DANGER"]
AtmAction = Literal["ALLOW", "VERIFY", "BLOCK"]
AtmStatus = Literal["READY", "WITHDRAW_ENABLED", "WITHDRAW_BLOCKED", "CALL_CENTER"]
CallcenterResolution = Literal["MAINTAINED", "RELEASED"]


# ── 인증 ────────────────────────────────────────────────────────────────────
class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=200)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: int
    username: str
    display_name: str
    role: Literal["user", "agent"]


# ── 친구 / 채팅 ──────────────────────────────────────────────────────────────
class FriendResponse(BaseModel):
    id: int
    username: str
    display_name: str


class ChatRoomResponse(BaseModel):
    id: int
    title: str
    last_message: str | None = None
    last_message_at: datetime | None = None


class MessageResponse(BaseModel):
    id: int
    chat_room_id: int
    sender_label: str
    content: str
    sent_at: datetime


class MessageCreateRequest(BaseModel):
    content: str = Field(min_length=1, max_length=2000)
    sender_label: str = Field(default="나", max_length=50)


# ── 분석 ────────────────────────────────────────────────────────────────────
class AnalyzeRequest(BaseModel):
    """문자 직접 입력(필수 기능) 또는 채팅 메시지 선택(message_id) 중 하나."""

    message: str | None = Field(default=None, max_length=2000)
    message_id: int | None = None


class AnalysisResponse(BaseModel):
    """PRD 5.2 출력 형식 + ATM 연동에 필요한 식별자."""

    analysis_id: int
    risk_level: RiskLevel
    risk_score: int
    reasons: list[str]
    summary: str
    detected_at: datetime
    message_text: str
    session_id: str | None = None
    atm_action: AtmAction


# ── ATM ─────────────────────────────────────────────────────────────────────
class AtmSessionResponse(BaseModel):
    """앱이 QR로 만들 세션 정보 (QR에는 session_id만 넣는다 — PRD 6.2)."""

    session_id: str
    risk_level: RiskLevel
    risk_score: int
    atm_status: AtmStatus


class AtmVerifyResponse(BaseModel):
    """라즈베리파이가 QR의 session_id로 조회하는 검증 결과 (PRD 5.8)."""

    session_id: str
    risk_level: RiskLevel
    risk_score: int
    action: AtmAction
    atm_status: AtmStatus
    detected_at: datetime
    summary: str
    reasons: list[str]


class AtmScanRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=50)
    atm_status: AtmStatus


class AtmSessionStatusResponse(BaseModel):
    """ATM이 몇 초마다 폴링하는 세션 상태 (콜센터 확인 결과 반영)."""

    session_id: str
    atm_status: AtmStatus
    callcenter_resolution: CallcenterResolution | None = None
    action: AtmAction


# ── 콜센터 ───────────────────────────────────────────────────────────────────
class CallcenterSessionResponse(BaseModel):
    """상담원 화면이 보는 확인 정보 (PRD 8.2)."""

    session_id: str
    analysis_id: int
    user_display_name: str
    risk_level: RiskLevel
    risk_score: int
    reasons: list[str]
    message_text: str
    atm_status: AtmStatus
    callcenter_resolution: CallcenterResolution | None = None
    detected_at: datetime
    scanned_at: datetime | None = None
    resolved_at: datetime | None = None


class CallcenterResolveRequest(BaseModel):
    resolution: CallcenterResolution
    note: str | None = Field(default=None, max_length=255)
