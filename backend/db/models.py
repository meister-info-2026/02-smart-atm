"""SQLAlchemy ORM 모델 (PRD 5.9 MySQL 스키마).

db-rules.md: 테이블/컬럼은 snake_case, 날짜/시간은 UTC로 저장하고 타임존 변환은
애플리케이션 레이어에서 처리한다.
"""
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    """타임존 정보를 뺀 UTC 현재 시각 (MySQL DATETIME과 호환)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


# 사용자 역할 (PRD 8: 콜센터 확인은 사용자 본인이 아니라 상담원이 한다)
ROLE_USER = "user"
ROLE_AGENT = "agent"


class User(Base):
    """사용자 계정. 비밀번호 원문은 저장하지 않고 Argon2 해시만 저장한다."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(50), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default=ROLE_USER)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class Friendship(Base):
    """친구 관계 (단방향 행 2개로 양방향을 표현한다)."""

    __tablename__ = "friendships"
    __table_args__ = (UniqueConstraint("user_id", "friend_user_id", name="uq_friendship"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    friend_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class ChatRoom(Base):
    """채팅방(문자 대화방)."""

    __tablename__ = "chat_rooms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    messages: Mapped[list["Message"]] = relationship(back_populates="chat_room")


class ChatRoomMember(Base):
    """채팅방 참여자."""

    __tablename__ = "chat_room_members"
    __table_args__ = (UniqueConstraint("chat_room_id", "user_id", name="uq_chat_member"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_room_id: Mapped[int] = mapped_column(ForeignKey("chat_rooms.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    joined_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class Message(Base):
    """채팅방 메시지 한 건 (분석 대상이 되는 '의심 문자')."""

    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_room_id: Mapped[int] = mapped_column(ForeignKey("chat_rooms.id"), nullable=False)
    sender_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    sender_label: Mapped[str] = mapped_column(String(50), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    sent_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    chat_room: Mapped[ChatRoom] = relationship(back_populates="messages")


class AnalysisResult(Base):
    """문자 분석 결과 (PRD 5.2 출력 형식 그대로 보존)."""

    __tablename__ = "analysis_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    chat_room_id: Mapped[int | None] = mapped_column(ForeignKey("chat_rooms.id"), nullable=True)
    message_id: Mapped[int | None] = mapped_column(ForeignKey("messages.id"), nullable=True)
    message_text: Mapped[str] = mapped_column(Text, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(20), nullable=False)
    risk_score: Mapped[int] = mapped_column(Integer, nullable=False)
    reasons: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    summary: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    engine: Mapped[str] = mapped_column(String(20), nullable=False, default="rule")
    detected_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    atm_session: Mapped["AtmSession | None"] = relationship(
        back_populates="analysis", uselist=False
    )


class AtmSession(Base):
    """ATM 연동 세션. QR에는 이 session_id만 들어간다 (PRD 6.2)."""

    __tablename__ = "atm_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    analysis_id: Mapped[int] = mapped_column(ForeignKey("analysis_results.id"), nullable=False)
    atm_status: Mapped[str] = mapped_column(String(30), nullable=False, default="READY")
    callcenter_resolution: Mapped[str | None] = mapped_column(String(20), nullable=True)
    callcenter_note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    scanned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    analysis: Mapped[AnalysisResult] = relationship(back_populates="atm_session")


class Device(Base):
    """제어 대상 장치 (db-rules.md 최소 테이블 — QR 카메라, 현금 배출 서보 등)."""

    __tablename__ = "devices"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class ControlLog(Base):
    """장치 제어 이력 (db-rules.md 최소 테이블). actor는 'user' 또는 'device'."""

    __tablename__ = "control_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), nullable=False)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    value: Mapped[str | None] = mapped_column(String(100), nullable=True)
    actor: Mapped[str] = mapped_column(String(20), nullable=False, default="device")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
